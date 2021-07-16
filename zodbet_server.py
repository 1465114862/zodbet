# coding=utf-8
# for ubuntu
#
# 在ubuntu系统下服务器中运行的zodgame虚拟股市自动买入卖出以及记录的脚本
# 可用crontab安排定时任务启动
# 需要cookie保持自动登录
# 需要Selenium,chromedriver,BeautifulSoup4
#
# 虚拟股市网址
jninvest_url="https://zodgame.xyz/plugin.php?id=jninvest"

#rlist=[50, 50, 34, 10, 0, 10, 50, 50] 2021年7月5日11点40分之前[003]退市前单次波动最大值
# 单次波动最大值
rlist=[50, 34, 10, 0, 10, 50, 50, 0]

from sys import path
import urllib.request
from urllib.request import urlopen
import csv
import time
import os
from bs4 import BeautifulSoup as bf
import os.path
import logging
import random
from datetime import datetime
import re
import math
import json
from selenium import webdriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.select import Select
from selenium.webdriver.common.by import By
import urllib.error

# 如果没有文件夹，将新建文件夹
root_path=str(os.path.dirname(os.path.abspath(__file__)))
dirpath=root_path+r'/data'
if (not os.path.exists(dirpath)):
    os.makedirs(dirpath)
dirpath=root_path+r'/invested'
if (not os.path.exists(dirpath)):
    os.makedirs(dirpath)
dirpath=root_path+r'/Logs'
if (not os.path.exists(dirpath)):
    os.makedirs(dirpath)
dirpath=root_path+r'/mystate'
if (not os.path.exists(dirpath)):
    os.makedirs(dirpath)
dirpath=root_path+r'/tempdata'
if (not os.path.exists(dirpath)):
    os.makedirs(dirpath)

# 创建一个logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)  # Log等级总开关

# 创建一个handler，用于写入日志文件
rq = time.strftime('%Y%m%d', time.localtime(time.time()))
log_path = root_path+'/Logs/'
log_name = log_path+ rq + 'log.log'
logfile = log_name
fh = logging.FileHandler(logfile, mode='a')
fh.setLevel(logging.DEBUG)  # 输出到file的log等级的开关

# 定义handler的输出格式
formatter = logging.Formatter("%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s")
fh.setFormatter(formatter)
logger.addHandler(fh)
# 使用logger.XX来记录错误,这里的"error"可以根据所需要的级别进行修改

# 初始配置文件，初次创建后需修改
configPath=root_path+r'/config.txt'
if(os.path.isfile(configPath)):
    tdict={}
    with open(configPath,'r',encoding='utf8') as f:
        tdict=json.loads(f.read(), strict=False)
    my_headers={'User-Agent':tdict['User-Agent']}
    my_headers.update({'Cookie':tdict['Cookie']})
    willing_to_buy=tdict['willing_to_buy']
    auto_trade=tdict['auto_trade']
    showwindow=tdict['showwindow']
    sell_prob_limit=tdict['sell_prob_limit']
    buy_prob_limit=tdict['buy_prob_limit']
    ten_hand_limit=tdict['ten_hand_limit']
else:
    my_headers = {
    'User-Agent':'请填入Request Headers的User-Agent',
    "Cookie":"请填入Request Headers的cookie",
    }
    # 购买意愿，1代表进行购入检查，0关闭
    willing_to_buy=1
    # 自动交易，1代表开启，0关闭
    auto_trade=1
    # （弃用）
    showwindow=0
    # 卖出概率限，默认0.1
    sell_prob_limit=0.1
    # 买入概率限，默认0.1
    buy_prob_limit=0.1
    # 10手最低收益，默认10
    ten_hand_limit=10
    tdict={}
    tdict.update(my_headers)
    tdict.update({'willing_to_buy':willing_to_buy})
    tdict.update({'auto_trade':auto_trade})
    tdict.update({'showwindow':showwindow})
    tdict.update({'sell_prob_limit':sell_prob_limit})
    tdict.update({'buy_prob_limit':buy_prob_limit})
    tdict.update({'ten_hand_limit':ten_hand_limit})
    with open(configPath,'w') as f:
        f.write(json.dumps(tdict))

# chrome driver尝试进入网站
def trytoopenpage(browser,url):
    resetlim=10
    for trytime in range(resetlim):
        try:
            browser.get(url)
        except:
            logger.info('未知错误，chrome尝试刷新页面，重试次数：'+str(trytime+1))
            sleeptime=random.randint(1, 5)
            time.sleep(sleeptime)
            if (trytime==resetlim-1):
                raise
            continue
        else:
            break

# 计算演化后仍没突破限制的概率，difference为跌停线与设定线差异/0.001，r为单次波动最大值，timeToEnd演化次数，initial初始位置
def probability_to_lose(difference,r,timeToEnd,initial):
    if(difference<-0.5):
        return 1
    if(r==0):
        return 1
    if(timeToEnd==0):
        return 1
    vec=[float(0)]*(difference+1)
    vec[initial]=float(1)
    for i in range(0,timeToEnd):
        newvec=[float(0)]*(difference+1)
        for j in range(min(r,difference),-1,-1):
            newvec[0]+=vec[j]*(r+1-j)/(2*r+1)
        for j in range(1,difference+1):
            for k in range(min(r+j,difference),max(0,-r+j)-1,-1):
                newvec[j]+=vec[k]/(2*r+1)
        vec=list(newvec)
    return sum(vec)

# 读取json
def readjsondict(tpath):
    tdict={}
    if(os.path.isfile(tpath)):
        with open(tpath,'r',encoding='utf8') as f:
            tdict=json.loads(f.read())
    return tdict

# 写入json
def writejsondict(tpath,tdict):
    with open(tpath,'w') as f:
        f.write(json.dumps(tdict))
    return

# 向记录dict的json文件添加key-value对，如果key存在便不写入
def addSingleDict(tpath,tdict):
    fdict=readjsondict(tpath)
    if list(tdict.keys())[0] in fdict:
        return
    fdict.update(tdict)
    writejsondict(tpath,fdict)
    return

# webdriver等待xpath引导的元素出现，10秒超时
def waitForXpath(browser,xpath):
    WebDriverWait(browser, 10).until(EC.presence_of_element_located((By.XPATH,xpath)))
    return browser.find_element(By.XPATH,xpath)

# webdriver点击对应xpath元素
def clickXpath(browser,xpath):
    theitem=waitForXpath(browser,xpath)
    browser.execute_script("arguments[0].click();", theitem)

# 解出设定概率，对应股的卖出线。由于函数性质，使用弦截法
def solveSellLimit(tobuy):
    dict_=readjsondict(root_path+'/tempdata/'+time.strftime('%Y%m%d', time.localtime(time.time()))+'.txt')
    x0=[int(round((tobuy[3]-float(dict_[tobuy[2]]))*1000*2)),0.1]
    x0[1]=probability_to_lose(x0[0],rlist[tobuy[0]],71-time.localtime(time.time()).tm_hour*3-int(math.floor(time.localtime(time.time()).tm_min/float(20))),0)-buy_prob_limit
    if(x0[1]<0):
        return
    x1=[int(round(((float(ten_hand_limit)/1000+float(dict_[tobuy[2]]))/0.95-float(dict_[tobuy[2]]))*1000)),0.1]
    x1[1]=probability_to_lose(x1[0],rlist[tobuy[0]],71-time.localtime(time.time()).tm_hour*3-int(math.floor(time.localtime(time.time()).tm_min/float(20))),0)-buy_prob_limit
    x2=[0,0.1]
    for i in range(100):
        x2[0]=int((float(x1[1])*float(x0[0])-float(x0[1])*float(x1[0]))/(float(x1[1])-float(x0[1])))
        if(x2[0]==x1[0] or x2[0]==x0[0]):
            if(abs(x1[0]-x0[0])==1):
                if(x1[1]<0):
                    tobuy[4]=x1[0]
                else:
                    tobuy[4]=x0[0]
                logger.info('得到具体值，tobuy:'+','.join(list(map(str,tobuy)))+'  x0:'+','.join(list(map(str,x0)))+'  x1:'+','.join(list(map(str,x1)))+'  x2:'+','.join(list(map(str,x2))))
                return
            if(x2[0]==x1[0]):
                x2[0]+=int((x0[0]-x2[0])/abs(x0[0]-x2[0]))
            else:
                x2[0]+=int((x1[0]-x2[0])/abs(x1[0]-x2[0]))
        x2[1]=probability_to_lose(x2[0],rlist[tobuy[0]],71-time.localtime(time.time()).tm_hour*3-int(math.floor(time.localtime(time.time()).tm_min/float(20))),0)-buy_prob_limit
        if(x0[1]*x2[1]>0):
            x0=x1.copy()
        x1=x2.copy()
    tobuy[4]=x2[0]
    logger.info('未能解得具体值，tobuy:'+','.join(list(map(str,tobuy)))+'  x0:'+','.join(list(map(str,x0)))+'  x1:'+','.join(list(map(str,x1)))+'  x2:'+','.join(list(map(str,x2))))
    return

# 自动买入
def auto_buy(tobuy,zb,invested):
    # webdriver初始化
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_experimental_option("excludeSwitches", ['enable-automation'])
    chrome_options.add_argument('headless')
    browser  = webdriver.Chrome(options=chrome_options)
    trytoopenpage(browser,jninvest_url)
    browser.delete_all_cookies()
    with open(root_path+(r'/jninvestCookies.txt'),'r',encoding='utf8') as f:
        listfCookies=json.loads(f.read())
    for cookie in listfCookies:
        browser.add_cookie(cookie)
    time.sleep(1)

    # 买入操作，价格高优先买入
    tobuy_=sorted(tobuy,key=(lambda x:[x[1],x[0]]))
    for i in range(len(tobuy_)):
        # 单支股票买入
        solveSellLimit(tobuy_[i])
        dontcycle=0
        onestackhand=10
        for j in range(len(invested)):
            if(invested[j][0]==tobuy_[i][2]):
                onestackhand-=int(invested[j][2])/100
        while(True):
            dontcycle+=1
            trytoopenpage(browser,jninvest_url)
            clickXpath(browser,'/html/body/div[5]/div[2]/table/tbody/tr[2]/td[1]/div[4]/div/div[2]/table/tbody/tr['+str(tobuy_[i][0]+2)+']/td[10]/a')
            hand_=waitForXpath(browser,'/html/body/div[1]/div/table/tbody/tr[2]/td[2]/form/div/table/tbody/tr[3]/td/table/tbody/tr/td[3]/p')
            hand=int(re.findall(r"\d+\.?d*",hand_.text)[0])
            handAvailable_=waitForXpath(browser,'/html/body/div[1]/div/table/tbody/tr[2]/td[2]/form/div/table/tbody/tr[2]/td[4]')
            handAvailable=int(math.floor(int(re.findall(r"\d+\.?d*",handAvailable_.text)[0])/100))
            zblimit=int(math.floor(zb/float(tobuy_[i][1])/100))
            handtoBuy=int(min([hand,handAvailable,zblimit,onestackhand,5]))
            time.sleep(1)
            if(hand==0):
                tempdict={'单日手数量耗尽':1}
                addSingleDict(root_path+'/tempdata/'+time.strftime('%Y%m%d', time.localtime(time.time()))+'.txt',tempdict)
                break
            if(handtoBuy<0.9):
                break
            if(dontcycle>50):
                break
            select=Select(waitForXpath(browser,'/html/body/div[1]/div/table/tbody/tr[2]/td[2]/form/div/table/tbody/tr[3]/td/table/tbody/tr/td[2]/select'))
            time.sleep(1)
            select.select_by_index(handtoBuy)
            time.sleep(1)
            clickXpath(browser,'/html/body/div[1]/div/table/tbody/tr[2]/td[2]/form/p/button')
            time.sleep(1)
            zb-=math.ceil(handtoBuy*tobuy_[i][1]*100)
            onestackhand-=handtoBuy
            tempdict={tobuy_[i][2]+'sell':tobuy_[i][4]}
            addSingleDict(root_path+'/tempdata/'+time.strftime('%Y%m%d', time.localtime(time.time()))+'.txt',tempdict)
            logger.info('buy:'+str(tobuy_[i][0]))
            logger.info('hand buy:'+str(handtoBuy))
            logger.info('zb:'+str(zb))


    time.sleep(2)
    browser.quit()
    return

# 自动卖出
def auto_sell(tosell):
    # webdriver初始化
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_experimental_option("excludeSwitches", ['enable-automation'])
    chrome_options.add_argument('headless')
    browser  = webdriver.Chrome(options=chrome_options)
    trytoopenpage(browser,jninvest_url)
    browser.delete_all_cookies()
    with open(root_path+(r'/jninvestCookies.txt'),'r',encoding='utf8') as f:
        listfCookies=json.loads(f.read())
    for cookie in listfCookies:
        browser.add_cookie(cookie)
    time.sleep(1)

    # 卖出操作
    tosell.sort()
    tosell.reverse()
    for i in range(len(tosell)):
        trytoopenpage(browser,jninvest_url)
        clickXpath(browser,'/html/body/div[5]/div[2]/table/tbody/tr[2]/td[1]/div[6]/div/div[2]/table/tbody/tr['+str(2+tosell[i])+']/td[6]/a')
        time.sleep(1)
        clickXpath(browser,'/html/body/div[1]/div[1]/table/tbody/tr[2]/td[2]/p/button[1]')
        time.sleep(1)
        logger.info('sell:'+str(tosell[i]))

    time.sleep(2)
    browser.quit()
    return

# 记录股价用，2d list转化为str
def table2d_to_str(the_table):
    strout=''
    for i in range(len(the_table)):
        for j in range(len(the_table[i])):
            strout+=the_table[i][j]
            if j!=len(the_table[i])-1:
                strout+=' '
        if i!=len(the_table)-1:
            strout+='\n'
    return strout

# 3种买入检测
def buy_test1(data,zb):
    return (float(data[2])<float(data[5])*0.75 or data[7]=='跌停') and int(data[3])>=100 and float(data[2])<float(zb)/100 and float(data[5])>0.05 and time.localtime(time.time()).tm_hour<=21

def buy_test2(data,zb,index):
    dict_=readjsondict(root_path+'/tempdata/'+time.strftime('%Y%m%d', time.localtime(time.time()))+'.txt')
    return  data[7]=='跌停' and int(data[3])>=100 and float(data[2])<float(zb)/100 and float(data[5])>0.05 and time.localtime(time.time()).tm_hour<=21 and probability_to_lose(int(round(float(dict_[data[0]])*200)),rlist[index],71-time.localtime(time.time()).tm_hour*3-int(math.floor(time.localtime(time.time()).tm_min/float(20))),0)<buy_prob_limit

def buy_test3(data,zb,index,invested):
    dict_=readjsondict(root_path+'/tempdata/'+time.strftime('%Y%m%d', time.localtime(time.time()))+'.txt')
    temp=1
    for j in range(len(invested)):
            if(invested[j][0]==data[0] and int(invested[j][2])==1000):
                temp=0
    return  temp==1 and data[7]=='跌停' and int(data[3])>=100 and float(data[2])<float(zb)/100  and time.localtime(time.time()).tm_hour<=21 and math.floor(1000*((2*float(data[5])-float(dict_[data[0]]))*0.95))-math.floor(1000*(float(dict_[data[0]])))>ten_hand_limit and probability_to_lose(int(round(((float(ten_hand_limit)/1000+float(dict_[data[0]]))/0.95-float(dict_[data[0]]))*1000)),rlist[index],71-time.localtime(time.time()).tm_hour*3-int(math.floor(time.localtime(time.time()).tm_min/float(20))),0)<buy_prob_limit

# log记录买入后失败概率
def logtheprob(data,index):
    dict_=readjsondict(root_path+'/tempdata/'+time.strftime('%Y%m%d', time.localtime(time.time()))+'.txt')
    logger.info(data[0]+'买入失败概率'+str(probability_to_lose(int(round(((float(ten_hand_limit)/1000+float(dict_[data[0]]))/0.95-float(dict_[data[0]]))*1000)),rlist[index],71-time.localtime(time.time()).tm_hour*3-int(math.floor(time.localtime(time.time()).tm_min/float(20))),0)))
    return  

# 检查买入
# data结构[投资代码,持有人,当前价格 (每股),可认购股份数量,涨/跌幅,昨日闭市报,今日涨/跌幅,状态]
# invested结构[投资代码,当前价格 (每股),您认购股份数量,认购股份平均价格]
# tobuy结构[代号(0~7),当前价格 (每股)f,投资代码,昨日闭市报f,卖出价差/0.001(-1代表无效)]
def check_buy(data,zb,will_buy,invested):
    if(will_buy==1):
        buy=[]
        tobuy=[]
        # 是否符合买入条件并记录
        for i in range(len(data)):
            if(data[i][7]=='跌停'):
                tempdict={data[i][0]:data[i][2]}
                addSingleDict(root_path+'/tempdata/'+time.strftime('%Y%m%d', time.localtime(time.time()))+'.txt',tempdict)
            if(buy_test3(data[i],zb,i,invested)):
                buy.append(data[i])
                tobuy.append([i,float(data[i][2]),data[i][0],float(data[i][5]),-1])
                logtheprob(data[i],i)
        # 对预买入股票进一步处理
        if(len(buy)!=0):
            buy_str=time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(time.time()))+'\n目前有符合购入条件股票，其信息如下：\n'+table2d_to_str(buy)
            logger.info(buy_str)
            if(auto_trade==1):
                tempdict=readjsondict(root_path+'/tempdata/'+time.strftime('%Y%m%d', time.localtime(time.time()))+'.txt')
                if '单日手数量耗尽' in tempdict:
                    logger.info('手数耗尽')
                else:
                    logger.info('auto buy')
                    auto_buy(tobuy,zb,invested)
    return

# 3种卖出检测
def sell_test1(bought):
    return ((bought[0]=='[003]' or bought[0]=='[013]' or bought[0]=='[015]') and (float(bought[2])>float(bought[5])*1.20 or bought[7]=='涨停') or (time.localtime(time.time()).tm_hour>=23 and time.localtime(time.time()).tm_min>=40)) or ((bought[0]!='[003]' and bought[0]!='[013]' and bought[0]!='[015]') and (float(bought[2])>float(bought[5])*1.07 or bought[7]=='涨停') or (time.localtime(time.time()).tm_hour>=23 and time.localtime(time.time()).tm_min>=40))

def sell_test2(bought):
    dict_=readjsondict(root_path+'/tempdata/'+time.strftime('%Y%m%d', time.localtime(time.time()))+'.txt')
    logger.info('卖出失败概率'+str(probability_to_lose(int(round((float(bought[2])-float(dict_[bought[0]]))*1000)),rlist[int(bought[8])],71-time.localtime(time.time()).tm_hour*3-int(math.floor(time.localtime(time.time()).tm_min/float(20))),int(round((float(bought[2])-float(dict_[bought[0]]))*1000)))))
    return  (bought[7]=='涨停' or probability_to_lose(int(round((float(bought[2])-float(dict_[bought[0]]))*1000)),rlist[int(bought[8])],71-time.localtime(time.time()).tm_hour*3-int(math.floor(time.localtime(time.time()).tm_min/float(20))),int(round((float(bought[2])-float(dict_[bought[0]]))*1000)))>sell_prob_limit) or (time.localtime(time.time()).tm_hour>=23 and time.localtime(time.time()).tm_min>=40)

def sell_test3(bought):
    dict_=readjsondict(root_path+'/tempdata/'+time.strftime('%Y%m%d', time.localtime(time.time()))+'.txt')
    temp=-1
    if bought[0]+'sell' in dict_:
        temp=dict_[bought[0]+'sell']
    return  ((temp>0 and (float(bought[2])-float(dict_[bought[0]]))*1000>temp) or bought[7]=='涨停' or probability_to_lose(int(round((float(bought[2])-float(dict_[bought[0]]))*1000)),rlist[int(bought[8])],71-time.localtime(time.time()).tm_hour*3-int(math.floor(time.localtime(time.time()).tm_min/float(20))),int(round((float(bought[2])-float(dict_[bought[0]]))*1000)))>sell_prob_limit) or (time.localtime(time.time()).tm_hour>=23 and time.localtime(time.time()).tm_min>=40)

# log记录卖出后失败概率
def logthesellprob(bought):
    dict_=readjsondict(root_path+'/tempdata/'+time.strftime('%Y%m%d', time.localtime(time.time()))+'.txt')
    logger.info(bought[0]+'卖出失败概率'+str(probability_to_lose(int(round((float(bought[2])-float(dict_[bought[0]]))*1000)),rlist[int(bought[8])],71-time.localtime(time.time()).tm_hour*3-int(math.floor(time.localtime(time.time()).tm_min/float(20))),int(round((float(bought[2])-float(dict_[bought[0]]))*1000)))))
    return  

# 检查卖出
# data结构[投资代码,持有人,当前价格 (每股),可认购股份数量,涨/跌幅,昨日闭市报,今日涨/跌幅,状态]
# invested结构[投资代码,当前价格 (每股),您认购股份数量,认购股份平均价格]
def check_sell(data,invested):
    tosell=[]
    sell=[]
    sell_state=[]
    bought=[]
    # 是否符合卖出条件并记录
    for j in range(len(invested)):
        for i in range(len(data)):
            if(data[i][0]==invested[j][0]):
                tempdata=data[i]
                tempdata.append(str(i))
                bought.append(tempdata)
    for i in range(len(invested)):
        if(sell_test3(bought[i])):
            tosell.append(i)
            sell.append(invested[i])     
            sell_state.append(bought[i])
            invested[i].append('预计收入:'+str(int(math.floor(float(invested[i][2])*(float(invested[i][1])*0.95))-math.floor(float(invested[i][2])*(float(invested[i][3]))))))
            logthesellprob(bought[i])
    # 对预卖出股票进一步处理
    if(len(sell)!=0):
        sell_str=time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(time.time()))+'\n目前有符合卖出条件股票，其信息如下：\n'+table2d_to_str(sell)+'\n其对应目前信息如下：\n'+table2d_to_str(sell_state)
        logger.info(sell_str)
        if(auto_trade==1):
            auto_sell(tosell)
    return

# 主函数
def get_and_sav_state(the_url,the_header,time_str):
    # urlopen获取数据
    req = urllib.request.Request(url=the_url, headers=the_header)
    # 错误重试10次
    resetlim=10
    for trytime in range(resetlim):
        try:
            with urlopen(req, timeout=30) as html:
                obj = bf(html.read(),'html.parser')
        except urllib.error.HTTPError :
            logger.info('urllib.error.HTTPError错误，正在尝试重试链接，重试次数：'+str(trytime+1))
            sleeptime=random.randint(1, 5)
            time.sleep(sleeptime)
            if (trytime==resetlim-1):
                raise
            continue
        except urllib.error.URLError :
            logger.info('urllib.error.URLError错误，正在尝试重试链接，重试次数：'+str(trytime+1))
            sleeptime=random.randint(1, 5)
            time.sleep(sleeptime)
            if (trytime==resetlim-1):
                raise
            continue
        except:
            logger.info('未知错误，正在尝试重试链接，重试次数：'+str(trytime+1))
            sleeptime=random.randint(1, 5)
            time.sleep(sleeptime)
            if (trytime==resetlim-1):
                raise
            continue
        else:
            break
    # 得到股价表
    table_html=obj.body.find('div',id='wp').find('div',align='center').table.find_all('tr')[1].td.find('div',class_='sd').find('div',class_='bm').find('div',class_='bm_c').table
    tr_html=table_html.find_all('tr')
    personal_information_html=obj.body.find('div',id='wp').find('div',align='center').table.find_all('tr')[0].find('td',width='180').find('div',class_='sd').find('div',class_='bm').find('div',class_='bm_c').ul
    personal_information_html_li_html=personal_information_html.find_all('li')
    invested_projects_html=obj.body.find('div',id='wp').find('div',align='center').table.find_all('tr')[1].td.find_all('div',class_='sd')[1].find('div',class_='bm').find('div',class_='bm_c').table
    invested_projects_html_tr_html=invested_projects_html.find_all('tr')
    data_now=[]
    # 记录数据到csv文件
    csvfile = open(root_path+'/data/' + time_str + '.csv', 'w',newline = '', encoding = "utf-8")
    writer = csv.writer(csvfile)
    del tr_html[0]
    for i in range(len(tr_html)):
        td_html=tr_html[i].find_all('td')
        del td_html[9]
        del td_html[0]
        row_=[]
        for j in range(len(td_html)):
            row_.append(td_html[j].text)
        writer.writerow(row_)
        data_now.append(row_)
    csvfile.close()
    csvfile = open(root_path+'/mystate/' + time_str + '.csv', 'w',newline = '', encoding = "utf-8")
    writer = csv.writer(csvfile)
    del personal_information_html_li_html[2]
    del personal_information_html_li_html[2]
    del personal_information_html_li_html[2]
    del personal_information_html_li_html[2]
    del personal_information_html_li_html[2]
    zb_now=float(re.findall(r"\d+\.?d*",personal_information_html_li_html[2].text)[0])
    row_=[]
    for j in range(5):
            row_.append(personal_information_html_li_html[j].text)
    writer.writerow(row_)
    csvfile.close()
    invested=[]
    # 优先检测卖出
    if(invested_projects_html_tr_html[1].td.text!='您暂时没有任何股票投资'):
        csvfile = open(root_path+'/invested/' + time_str + '.csv', 'w',newline = '', encoding = "utf-8")
        writer = csv.writer(csvfile)
        del invested_projects_html_tr_html[0]
        for i in range(len(invested_projects_html_tr_html)):
            td_html=invested_projects_html_tr_html[i].find_all('td')
            del td_html[5]
            del td_html[0]
            row_=[]
            for j in range(len(td_html)):
                row_.append(td_html[j].text)
            writer.writerow(row_)
            invested.append(row_)
        csvfile.close()
        check_sell(data_now,invested)
    # 检测买入
    check_buy(data_now,zb_now,willing_to_buy,invested)


# __main__
try:
    now_time=time.localtime(time.time())
    if now_time.tm_hour>=9 and datetime.now().isoweekday()!=7:
        sleeptime=random.randint(0, 15)
        time.sleep(sleeptime) # 启动时间有15秒随机，防止被识别访问时间模式后拒绝访问
        now_time=time.localtime(time.time())
        this_time=time.strftime('%Y-%m-%d-%H-%M-%S',now_time)
        get_and_sav_state(jninvest_url,my_headers,this_time)
except (SystemExit, KeyboardInterrupt):
    raise
except Exception as e:
    logger.error('Unclassified', exc_info=True)