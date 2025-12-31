import scrapy
import unicodedata
import datetime
import configparser
import mysql.connector
import os
import logging
import json
import requests
#import resend #no longer using resend sdk, just direct requests
#import mailtrap as mt as above
from mysql.connector.constants import ClientFlag
from tmmis_searcher.items import AgendaItem
from scrapy import signals
from pydispatch import dispatcher
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from scrapy.mail import MailSender #for gmail
from urllib.parse import quote
from pprint import pformat
from scrapy.http.cookies import CookieJar
from datetime import tzinfo
from curl_cffi import requests as curl_requests
from scrapy.utils.versions import scrapy_components_versions

testemail = 1 #normally 0
sendemails = 1 #normally 1
updatedb = 1 #normally 1
debugemaillimit = 0 ## normally 0; if 1, it only processes searches created by gabe@pwd.ca
emailchannel = 'resend' # sendgrid, resend, mailtrap, gmail
#tempmessage = '<br>' + "<b>NOTE: </b> On November 17th 2025, the City of Toronto made changes to TMMIS which made it impossible for Tabs to access TMMIS data. I've now fixed this, but it means that no notifications were sent between Nov 18 - Nov 22 2025. Sorry for the inconvenience. - Gabe." + '<br>' # string beginning and ending with <br> ,  or ''
tempmessage = ''
tempfromdate = '' # 'YYYY-MM-DD' or ''

slackts = ''
resenddailyquotaremaining = "undefined"

proxy = ""

lg = logging.getLogger()
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)
#logging.getLogger().setLevel(logging.INFO)
lg.info("SENDEMAILS: "+str(sendemails))
lg.info("TEMPMESSAGE: "+tempmessage)
lg.info("TEMPFROMDATE: "+tempfromdate)


class TmmisSearchSpider(scrapy.Spider):
	name = 'tmmis-search'
	allowed_domains = ['toronto.ca']
	download_delay = 1.5
	conf = { }

	def __init__(self):
		dispatcher.connect(self.spider_closed, signals.spider_closed)

	def get_csrf_tokens(self):
		global proxy

		session = curl_requests.Session()
		session.get('https://secure.toronto.ca/council/', impersonate="chrome120", proxy=proxy)
		session.get('https://secure.toronto.ca/council/api/csrf.json', impersonate="chrome120", proxy=proxy).raise_for_status()

		cookies_dict = dict(session.cookies)
		xsrf_token = cookies_dict.get('XSRF-TOKEN')
		if not xsrf_token:
			lg.error(f'XSRF-TOKEN not found. Available cookies: {list(cookies_dict.keys())}')
			#raise Exception(f'XSRF-TOKEN not found. Available cookies: {list(cookies_dict.keys())}')

		return cookies_dict, xsrf_token

	def get_searchphrase(self,id):
		#given the id of a record in the searches table, returns the associated searchphrase
		if self.settings.get('MYSQL_USER'):
			conf = {
				'user': self.settings.get('MYSQL_USER'),
				'password': self.settings.get('MYSQL_PASSWORD'),
				'host': self.settings.get('MYSQL_HOST'),
				'database': self.settings.get('MYSQL_DATABASE'),
			 	'raise_on_warnings': True
			}
		else:
			lg.error('mysql config failure')
			#raise Exception('mysql config failure')

		conn = mysql.connector.connect(**conf)
		cursor = conn.cursor()
		if str(id) != "":
			cursor.execute('SELECT searchphrase FROM `searches` WHERE id = ' + str(id) + ';')
			for row in cursor:
				if row:
					return row[0]
		else:
			pass

	async def spider_closed(self, spider):
		global sendemails
		global tempmessage
		global lg

		global slackts
		global resenddailyquotaremaining

		if self.settings.get('MYSQL_USER'):
			conf = {
				'user': self.settings.get('MYSQL_USER'),
				'password': self.settings.get('MYSQL_PASSWORD'),
				'host': self.settings.get('MYSQL_HOST'),
				'database': self.settings.get('MYSQL_DATABASE'),
			 	'raise_on_warnings': True
			}
		else:
			raise Exception('mysql config failure')	

		#send emails now
		conn = mysql.connector.connect(**conf)
		conn2 = mysql.connector.connect(**conf)
		cursor = conn.cursor(dictionary=True)
		cursor.execute('SELECT * FROM notifications WHERE emailsent=0 ORDER BY id ASC;')
		lg.info("--------- reviewing notifications")
		emailtext = ""
		lastid = ""
		lastemail = ""
		for row in cursor:
			if emailtext == "":
				lg.debug("A: "+str(row['id']))
				emailtext = "<b>Your search for " + self.get_searchphrase(row['id']) + " returned the following new results:</b><br><br>"
			if lastid == "":
				lg.debug("B: "+str(row['id'])+" "+row['title'])
				#this is the first record; add to the email we're preparing
				emailtext += row['title'] + ' <a href="https://secure.toronto.ca/council/agenda-item.do?item=' + row['reference'] + '">' + row['reference'] + '</a> ' + row['decisionBodyName'] + " " + row['meetingdate'] + "<br><br>"
				lastid = row['id']
				lastemail = row['email']
			elif row['id'] == lastid:
				lg.debug("C: "+str(row['id'])+" "+row['title'])
				#this is a subsequent record; add it to the email we're preparing
				emailtext += row['title'] + ' <a href="https://secure.toronto.ca/council/agenda-item.do?item=' + row['reference'] + '">' + row['reference'] + '</a> ' + row['decisionBodyName'] + " " + row['meetingdate'] + "<br><br>"
				lastid = row['id']
				lastemail = row['email']
			else:
				lg.debug("D: "+str(lastid))
				#this is part of a separate notification, so first let's send the email for the previous one
				if tempmessage:
					emailtext += tempmessage
				emailtext += "<br>To permanently stop receiving notifications for this search, click here: http://pwd.ca/tabs/unsubscribe.php?e=" + quote(lastemail) + "&i=" + str(lastid)
				if sendemails:
					await self.send_email(lastemail,"Tabs Toronto notification: "+self.get_searchphrase(lastid),emailtext)
					lg.info("sent email to "+ lastemail + " for " + str(lastid))
				else:
					lg.info("_didn't_ send email to "+ lastemail + " for " + str(lastid))

				cursor2 = conn2.cursor()
				lg.info('ABOUT TO RUN: ' + 'UPDATE notifications SET emailsent=1 WHERE id = "' + str(lastid) + '";')
				if updatedb:
					cursor2.execute('UPDATE notifications SET emailsent=1 WHERE id = "' + str(lastid) + '";')
					conn2.commit()

				lg.debug("D2: "+str(row['id']))
				#start preparing the next email
				emailtext = "<b>Your search for " + self.get_searchphrase(row['id']) + " returned the following new results:</b><br><br>"
				emailtext += row['title'] + ' <a href="https://secure.toronto.ca/council/agenda-item.do?item=' + row['reference'] + '">' + row['reference'] + '</a> ' + row['decisionBodyName'] + " " + row['meetingdate'] + "<br><br>"
				lastid = row['id']
				lastemail = row['email']

		if lastid == "":
			#there are no emails to send
			pass
		else:
			lg.debug("E+")
			lg.debug(lastid)
			#send the final email
			if tempmessage:
				emailtext += tempmessage
			emailtext += "<br>To permanently stop receiving notifications for this search, click here: http://pwd.ca/tabs/unsubscribe.php?e=" + quote(lastemail) + "&i=" + str(lastid)
			if sendemails:
				await self.send_email(lastemail,"Tabs Toronto notification: "+self.get_searchphrase(lastid),emailtext)
				lg.info("sent email to "+ lastemail + " for " + str(lastid))
			else:
				lg.info("_didn't_ send email to "+ lastemail + " for " + str(lastid))

			cursor2 = conn2.cursor()
			lg.info('ABOUT TO RUN: ' + 'UPDATE notifications SET emailsent=1 WHERE id = "' + str(lastid) + '";')
			if updatedb:
				cursor2.execute('UPDATE notifications SET emailsent=1 WHERE id = "' + str(lastid) + '";')
				conn2.commit()
		lg.info("--------- finished notifications/emails")
		slackmsg = "done\n"
		slackresp = requests.post("https://slack.com/api/chat.postMessage",json={"thread_ts": slackts,"channel":"C0A5AKWV682","text": slackmsg}, headers={"Authorization": "Bearer "+self.settings.get('SLACK_TOKEN'),"Content-type": "application/json; charset=utf-8"})

		#post email stats to Slack
		if emailchannel == "sendgrid":
			sg = SendGridAPIClient(self.settings.get('SENDGRID_API_KEY'))
			sgresponse = sg.client.stats.get(query_params={"start_date": datetime.datetime.today().strftime('%Y-%m-%d')})
			sgstatsjson = json.loads(sgresponse.body)
			slackmsg = "Sendgrid stats (today): requests: " + pformat(sgresponse) + "\n"
			try:
				if sgstatsjson[0]["date"] == datetime.datetime.today().strftime('%Y-%m-%d'):
					slackmsg = "Sendgrid stats (today): Requests: " + str(sgstatsjson[0]["stats"][0]["metrics"]["requests"]) + " / delivered: " + str(sgstatsjson[0]["stats"][0]["metrics"]["delivered"]) 
				else: 
					slackmsg = "error (A) parsing sendgrid stats response"
			except: 
				slackmsg = "error (B) parsing sendgrid stats response"
			slackresp = requests.post("https://slack.com/api/chat.postMessage",json={"thread_ts": slackts,"channel":"C0A5AKWV682","text": slackmsg}, headers={"Authorization": "Bearer "+self.settings.get('SLACK_TOKEN'),"Content-type": "application/json; charset=utf-8"})
			lg.info(slackmsg)
		elif emailchannel == "resend":
			try:
				if int(resenddailyquotaremaining) < 2:
					slackmsg = "@gabe resend daily quota almost exhausted (" + resenddailyquotaremaining + ")"
					slackresp = requests.post("https://slack.com/api/chat.postMessage",json={"thread_ts": slackts,"channel":"C0A5AKWV682","text": slackmsg}, headers={"Authorization": "Bearer "+self.settings.get('SLACK_TOKEN'),"Content-type": "application/json; charset=utf-8"})		
			except (TypeError, ValueError):
				pass
			slackmsg = "resend daily quota remaining: " + str(resenddailyquotaremaining)
			slackresp = requests.post("https://slack.com/api/chat.postMessage",json={"thread_ts": slackts,"channel":"C0A5AKWV682","text": slackmsg}, headers={"Authorization": "Bearer "+self.settings.get('SLACK_TOKEN'),"Content-type": "application/json; charset=utf-8"})
			lg.info(slackmsg)
		elif emailchannel == "mailtrap":
			mtresp = requests.get("https://mailtrap.io/api/accounts/2566853/stats?start_date="+datetime.datetime.today().strftime('%Y-%m-%d')+"&end_date="+datetime.datetime.today().strftime('%Y-%m-%d'), headers={"Accept": "application/json","Api-Token": self.settings.get('MAILTRAP_API_KEY')})
			slackmsg = "mailtrap daily quota remaining: " + str(150-int(mtresp.json()["delivery_count"]))
			slackresp = requests.post("https://slack.com/api/chat.postMessage",json={"thread_ts": slackts,"channel":"C0A5AKWV682","text": slackmsg}, headers={"Authorization": "Bearer "+self.settings.get('SLACK_TOKEN'),"Content-type": "application/json; charset=utf-8"})
			lg.info(slackmsg)
		else: # we assume gmail
			slackmsg = "emails sent thru gmail smtp, no stats available"
			slackresp = requests.post("https://slack.com/api/chat.postMessage",json={"thread_ts": slackts,"channel":"C0A5AKWV682","text": slackmsg}, headers={"Authorization": "Bearer "+self.settings.get('SLACK_TOKEN'),"Content-type": "application/json; charset=utf-8"})
			lg.info(slackmsg)

			##################################################

	async def send_email(self,to,subject,content):
		global emailchannel
		global resenddailyquotaremaining

		if emailchannel == "sendgrid":
			message = Mail(
	    		from_email='tabstoronto@pwd.ca',
	   			to_emails=to,
	    		subject=subject,
	    		html_content=content)
			lg.debug(" @@ SENDGRID email starting")
			try:
				if self.settings.get('SENDGRID_API_KEY'):	
					sg = SendGridAPIClient(self.settings.get('SENDGRID_API_KEY'))
				else:
					raise Exception("sendgrid api key error")
	
				response = sg.send(message)
				lg.debug(" @@ SENDGRID email done")
			except Exception as e:
				print(e.message)
		elif emailchannel == "resend":
			resendresp = requests.post("https://api.resend.com/emails",json={"from":'tabstoronto@pwd.ca',"to": to, "subject": subject, "html": content}, headers={"Authorization": "Bearer "+self.settings.get('RESEND_API_KEY'),"Content-type": "application/json"})
			if isinstance(resendresp.headers['x-resend-daily-quota'], int):
				resenddailyquotaremaining = 100 - int(resendresp.headers['x-resend-daily-quota'])
			lg.info("resend email sent: "+to)
		elif emailchannel == "mailtrap":
			mtresp = requests.post("https://send.api.mailtrap.io/api/send", json={"from": {"email": "tabstoronto@pwd.ca", "name": "Tabs Toronto"}, "to": [{"email": to}], "subject": subject, "text": content}, headers={"Content-Type": "application/json","Accept": "application/json","Api-Token": self.settings.get('MAILTRAP_API_KEY')})
			lg.info("mailtrap email sent: "+to)
		else: #we assume emailchannel = "gmail"
			lg.debug(" @@@@@ gmail")
			mailer = MailSender(mailfrom='tabstoronto@pwd.ca',
				smtpuser=self.settings.get('GMAIL_USERNAME'),smtphost="smtp.gmail.com", 
				smtpport=587, smtppass=self.settings.get('GMAIL_PASSWORD'), smtptls=1)
			lg.debug(" @@@@@ email about to send, gmail")
			return mailer.send(to=to, subject=subject, body=content)

	def start_requests(self):
		global slackts
		global proxy
		global testemail
		global resenddailyquotaremaining

		PROXIES = self.settings.get('PROXIES')
		#set proxy to PROXIES[0] (or "") for no proxy
		#proxy = PROXIES[random.randint(1, len(PROXIES)-1)]
		proxy = PROXIES[1+ (datetime.datetime.now().microsecond % 2)] #"randomly" picks 1 or 2

		slackmsg = "Run start: "
		for name, version in scrapy_components_versions():
			if name == "Platform":
				slackmsg += version
		proxy_display = ""
		_,_,proxy_display = proxy.partition("@")
		slackmsg += " / Proxy " + proxy_display
		slackresp = requests.post("https://slack.com/api/chat.postMessage",json={"channel":"C0A5AKWV682","text": slackmsg}, headers={"Authorization": "Bearer "+self.settings.get('SLACK_TOKEN'),"Content-type": "application/json; charset=utf-8"})
		lg.info(slackmsg)
		try:
			slackdata = slackresp.json()
		except requests.JSONDecodeError:
			#error
			lg.error("json decode error")
		slackts = slackdata['ts']

		mycookies, xsrf_token = self.get_csrf_tokens()

		if testemail:
			if emailchannel == "resend":
				resendresp = requests.post("https://api.resend.com/emails",json={"from":'tabstoronto@pwd.ca',"to": "gabe@pwd.ca", "subject": "Tabs Toronto Test", "html": "test"}, headers={"Authorization": "Bearer "+self.settings.get('RESEND_API_KEY'),"Content-type": "application/json"})
				resenddailyquotaremaining = 100 - int(resendresp.headers['x-resend-daily-quota'])
			elif emailchannel == "mailtrap":
				mtresp = requests.post("https://send.api.mailtrap.io/api/send", json={"from": {"email": "tabstoronto@pwd.ca", "name": "Tabs Toronto"}, "to": [{"email": "gabe@pwd.ca"}], "subject": "Tabs Toronto Test", "text": "test"}, headers={"Content-Type": "application/json","Accept": "application/json","Api-Token": self.settings.get('MAILTRAP_API_KEY')})
			elif emailchannel == "gmail":
				lg.debug(" @@@@@ gmail")
				mailer = MailSender(mailfrom='tabstoronto@pwd.ca',
					smtpuser=self.settings.get('GMAIL_USERNAME'),smtphost="smtp.gmail.com", 
					smtpport=587, smtppass=self.settings.get('GMAIL_PASSWORD'), smtptls=1)
				lg.debug(" @@@@@ email about to send, gmail")
				to = "gabe@pwd.ca"
				subject = "Tabs Toronto Test"
				content = "test"
				mailer.send(to=to, subject=subject, body=content)
			slackmsg = "Sent test email"
			slackresp = requests.post("https://slack.com/api/chat.postMessage",json={"channel":"C0A5AKWV682","text": slackmsg}, headers={"Authorization": "Bearer "+self.settings.get('SLACK_TOKEN'),"Content-type": "application/json; charset=utf-8"})
			#os._exit(0)

		yield scrapy.Request(
			'https://secure.toronto.ca/council/',
			self.parse_first_requests,
			dont_filter=True,
			meta={'cookies': mycookies, 'xsrf_token': xsrf_token, "proxy": proxy, "slackts": slackdata['ts'] }
		)


	def parse_first_requests(self, response):
		global tempfromdate
		global debugemaillimit

		# Get cookies and XSRF token from meta (set by start_requests using curl_cffi)
		mycookies = response.meta['cookies']
		xsrf_token = response.meta['xsrf_token']

		#lg.debug("@@@ xsrf_token:" + xsrf_token)

		if self.settings.get('MYSQL_USER'):
			conf = {
				'user': self.settings.get('MYSQL_USER'),
				'password': self.settings.get('MYSQL_PASSWORD'),
				'host': self.settings.get('MYSQL_HOST'),
				'database': self.settings.get('MYSQL_DATABASE'),
			 	'raise_on_warnings': True
			}
		else:
			raise Exception('mysql config failure')	

		conn = mysql.connector.connect(**conf)
		cursor = conn.cursor()
		if debugemaillimit:
			cursor.execute('SELECT searchphrase,id,email FROM `searches` WHERE emailvalidated AND email="gabe@pwd.ca";')
		else:
			cursor.execute('SELECT searchphrase,id,email FROM `searches` WHERE emailvalidated;')
		rows = cursor.fetchall()

		headers = {
			"Accept": "application/json, text/plain, */*",
			"Accept-Language": "en-CA,en;q=0.9",
			"Connection": "keep-alive",
			"Content-Type": "application/json",
			"Origin": "https://secure.toronto.ca",
			"Sec-Fetch-Dest": "document",
			"Sec-Fetch-Mode": "navigate",
			"Sec-Fetch-Site": "none",
			"Sec-Fetch-User": "?1",
			"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
			"X-XSRF-TOKEN": xsrf_token,
			"sec-ch-ua-mobile": "?0",
			"sec-ch-ua-platform": '"macOS"',
		}

		lg.debug("ROWS: "+pformat(rows))
		for row in rows:
			if row:
				if tempfromdate != '':
					fromDate = datetime.datetime.strptime(tempfromdate,'%Y-%m-%d')
				else:
					fromDate = datetime.datetime.today()
				fromDate = fromDate.replace(hour=0, minute=0, second=0, microsecond=0)
				fromDate = fromDate.astimezone(datetime.timezone.utc)
				#lg.debug("FROMDATE: "+pformat(fromDate))

				thisurl = 'https://secure.toronto.ca/council/api/multiple/agenda-items.json?pageNumber=0&pageSize=50&sortOrder=meetingDate%20desc,referenceSort'
				body = '{"includeTitle":true,"includeSummary":true,"includeRecommendations":true,"includeDecisions":true,"meetingFromDate":"' + fromDate.strftime("%Y-%m-%dT%H:%M:%S.%fZ") + '","meetingToDate":null,"word":"'+ row[0].replace('"','\\"') +'","includeAttachments":true}'

				yield scrapy.Request(thisurl, self.parse, method='POST', dont_filter=True, headers=headers, body=body, cookies=mycookies, meta=dict(id=row[1],email=row[2],slackts=response.meta['slackts']))

		cursor.close()

	def parse(self, response):
		global lg

		if response.status != 200:
			#do debug output and die.
			lg.error("@@@RESPONSE: "+str(response.status))
			lg.error("BODY:"+pformat(response.body))
			lg.error("REQ-HEADERS:"+pformat(response.request.headers))
			lg.error("REQ-COOKIES:"+pformat(response.request.cookies))
			lg.error("REQ-BODY:"+pformat(response.request.body))
			
			slackmessage = "UNEXPECTED RESPONSE\n" + "RESPONSE: "+str(response.status) + \
				"BODY:"+pformat(response.body) + "\n" + \
				"REQ-HEADERS:"+pformat(response.request.headers) + "\n" + \
				"REQ-COOKIES:"+pformat(response.request.cookies) + "\n" + \
				"REQ-BODY:"+pformat(response.request.body) + "\n"

			#send Slack notification
			slackresp = requests.post("https://slack.com/api/chat.postMessage",json={"thread_ts": response.meta['slackts'],"channel":"C0A5AKWV682","text": slackmessage}, headers={"Authorization": "Bearer "+self.settings.get('SLACK_TOKEN'),"Content-type": "application/json; charset=utf-8"})

		else: #RESPONSE LOOKS GOOD
			jsonresponse = json.loads(response.body)
			for r in jsonresponse["Records"]:
				item = AgendaItem()
				item['meetingDate'] = datetime.datetime.utcfromtimestamp(r['meetingDate']/1000).strftime("%Y-%m-%d")
				item['reference'] = r['reference']
				item['agendaItemTitle'] = r['agendaItemTitle']
				item['decisionBodyName'] = r['decisionBodyName']
				item['search_id'] = response.meta['id']
				item['email'] = response.meta['email']
				#lg.debug("ITEM: " + pformat(item))

				slackmessage = "hit: "+str(response.meta['id'])+"\n"
				slackresp = requests.post("https://slack.com/api/chat.postMessage",json={"thread_ts": response.meta['slackts'],"channel":"C0A5AKWV682","text": slackmessage}, headers={"Authorization": "Bearer "+self.settings.get('SLACK_TOKEN'),"Content-type": "application/json; charset=utf-8"})

				yield item

	def errback(self, failure):
		global lg
		# log all failures
		lg.debug("FAILURE:" + pformat(failure))

	
