# coding=utf-8
# for ubuntu
#
# python 3.8.8
# 配合zodbet_server.py，置于同一目录，用于获取chrome的cookie
# 在打开前，确保已经在chrome中登陆zodgame账号，并关闭chrome
# 需要Selenium,chromedriver,BeautifulSoup4
jninvest_url="https://zodgame.xyz/plugin.php?id=jninvest"
import json
from selenium import webdriver
from bs4 import BeautifulSoup as bf
from selenium.common.exceptions import TimeoutException
import os
print("准备得到Cookies")
chrome_options = webdriver.ChromeOptions()
chrome_options.add_experimental_option("excludeSwitches", ['enable-automation'])
chrome_options.add_argument('headless')
chrome_options.add_argument(r"user-data-dir=/home/用户名/.config/google-chrome") #ubuntu用户设置文件夹
#chrome_options.add_argument(r"user-data-dir=C:\Users\用户名\AppData\Local\Google\Chrome\User Data") #windows用户设置文件夹
browser  = webdriver.Chrome(options=chrome_options)
browser.get(jninvest_url)
dictCookies=browser.get_cookies()
jsonCookies=json.dumps(dictCookies)
print(jsonCookies)
# 保存cookies
root_path=str(os.path.dirname(os.path.abspath(__file__)))
with open(root_path+r'/jninvestCookies.txt','w') as f:
    f.write(jsonCookies)
# 检测是否登陆成功，即cookie是否可用
html=browser.page_source
obj = bf(html,'html.parser')
table_html=obj.body.find('div',id='wp').find('div',align='center').table.find_all('tr')[1].td.find('div',class_='sd').find('div',class_='bm').find('div',class_='bm_c').table.find_all('tr')[0].find_all('td')[0]
if(table_html.text=='投资项目'):
    print('成功')
else:
    print('失败')
# 退出
browser.quit()
print("已保存Cookies")

