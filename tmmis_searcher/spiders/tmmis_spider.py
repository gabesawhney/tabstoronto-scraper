import scrapy
import unicodedata
import datetime
import configparser
import mysql.connector
import os
import logging
import json
from mysql.connector.constants import ClientFlag
from tmmis_searcher.items import AgendaItem
from scrapy import signals
from pydispatch import dispatcher
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from urllib.parse import quote
from pprint import pformat
from scrapy.http.cookies import CookieJar
from datetime import tzinfo

sendemails = 1
#tempmessage = '<br>' + "<b>NOTE: </b> On December 20th 2022, the City of Toronto launched an updated version of TMMIS, called 'www.toronto.ca/council'. Due to this change, Tabs Toronto needed to be updated, and between then and January 8th 2023, notifications were not sent. <br><br>You may receive a large volume of notifications on or after January 8th, as the Tabs system catches up. You may also receive a larger volume of notifications on an ongoing basis, because the 'new TMMIS' also returns agenda items where the search terms match <I>within documents attached to the item</I>. As always, if you find that you're receiving more notifications than you'd like, you can delete your search using the link below, and create a new, more specific search at <a href='http://pwd.ca/tabs'>pwd.ca/tabs</a>." + '<br>' # string beginning and ending with <br> ,  or ''
tempmessage = ''
tempfromdate = '' # 'YYYY-MM-DD' or ''

lg = logging.getLogger()
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)
lg.info("SENDEMAILS: "+str(sendemails))
lg.info("TEMPMESSAGE: "+tempmessage)
lg.info("TEMPFROMDATE: "+tempfromdate)


class TmmisSearchSpider(scrapy.Spider):

	name = 'tmmis-search'
	allowed_domains = ['toronto.ca']
	conf = { }


	def __init__(self):
		dispatcher.connect(self.spider_closed, signals.spider_closed)

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
			raise Exception('mysql config failure')	

		conn = mysql.connector.connect(**conf)
		cursor = conn.cursor()
		if str(id) != "":
			cursor.execute('SELECT searchphrase FROM `searches` WHERE id = ' + str(id) + ';')
			for row in cursor:
				if row:
					return row[0]
		else:
			pass

	def spider_closed(self, spider):
		global sendemails
		global tempmessage
		global lg

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
					self.send_email(lastemail,"Tabs Toronto notification: "+self.get_searchphrase(lastid),emailtext)
					lg.info("sent email to "+ lastemail + " for " + str(lastid))
				else:
					lg.info("_didn't_ send email to "+ lastemail + " for " + str(lastid))
				lg.info("sent email to "+ lastemail + " for " + str(lastid))

				cursor2 = conn2.cursor()
				lg.info('ABOUT TO RUN: ' + 'UPDATE notifications SET emailsent=1 WHERE id = "' + str(lastid) + '";')
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
				self.send_email(lastemail,"Tabs Toronto notification: "+self.get_searchphrase(lastid),emailtext)
				lg.info("sent email to "+ lastemail + " for " + str(lastid))
			else:
				lg.info("_didn't_ send email to "+ lastemail + " for " + str(lastid))

			cursor2 = conn2.cursor()
			lg.info('ABOUT TO RUN: ' + 'UPDATE notifications SET emailsent=1 WHERE id = "' + str(lastid) + '";')
			cursor2.execute('UPDATE notifications SET emailsent=1 WHERE id = "' + str(lastid) + '";')
			conn2.commit()
		lg.info("--------- finished notifications/emails")

	def send_email(self,to,subject,content):
		message = Mail(
    		from_email='tabstoronto@pwd.ca',
   			to_emails=to,
    		subject=subject,
    		html_content=content)
		try:
			if self.settings.get('SENDGRID_API_KEY'):	
				sg = SendGridAPIClient(self.settings.get('SENDGRID_API_KEY'))
			else:
				raise Exception("sendgrid api key error")

			response = sg.send(message)
		except Exception as e:
			print(e.message)

	def start_requests(self):
		mycookies = ""
		#first request
		thisurl = 'https://secure.toronto.ca/council/'
		yield scrapy.Request(thisurl, self.parse_first_requests, dont_filter=True, meta={'cookiejar': mycookies})

		#second request
		thisurl = 'https://secure.toronto.ca/council/api/csrf.json'
		yield scrapy.Request(thisurl, self.parse_first_requests, method='GET', dont_filter=True, meta={'cookiejar': mycookies})



	def parse_first_requests(self, response):
		global tempfromdate

		if response.url == 'https://secure.toronto.ca/council/':
			pass
		else:
			mycookies = {}
			cookieJar = response.meta.setdefault('cookie_jar', CookieJar())
			cookieJar.extract_cookies(response, response.request)
			for cooki in cookieJar: 
				mycookies[cooki.name] = cooki.value

			if mycookies['XSRF-TOKEN']:
				pass
			else:
				raise Exception('XSRF value is missing')
		
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
			cursor.execute('SELECT searchphrase,id,email FROM `searches` WHERE emailvalidated;')
			rows = cursor.fetchall()

			xsrftoken = ""
			body = ""
			headers = {
	 			"Accept": "application/json, text/plain, */*", "Accept-Language": "en-GB,en-US;q=0.9,en;q=0.8", "Connection": "keep-alive", "Content-Type": "application/json", "Origin": "https://secure.toronto.ca", "Referer": "https://secure.toronto.ca/council/", "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-origin", "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36", "sec-ch-ua": "\"Not?A_Brand\";v=\"8\", \"Chromium\";v=\"108\", \"Google Chrome\";v=\"108\"", "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": "\"macOS\"",
	    			"X-XSRF-TOKEN": mycookies['XSRF-TOKEN'],
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
					lg.debug("FROMDATE: "+pformat(fromDate))
					
					thisurl = 'https://secure.toronto.ca/council/api/multiple/agenda-items.json?pageNumber=0&pageSize=50&sortOrder=meetingDate%20desc,referenceSort'
					body = '{"includeTitle":true,"includeSummary":true,"includeRecommendations":true,"includeDecisions":true,"meetingFromDate":"' + fromDate.strftime("%Y-%m-%dT%H:%M:%S.%fZ") + '","meetingToDate":null,"word":"'+ row[0] +'","includeAttachments":true}'

					yield scrapy.Request(thisurl, self.parse, method='POST', dont_filter=True, headers=headers, body=body, cookies=mycookies, meta=dict(id=row[1],email=row[2]))

			cursor.close()


	def parse(self, response):
		global lg
		jsonresponse = json.loads(response.body)
		#lg.debug("RESPONSE: "+pformat(jsonresponse))
		for r in jsonresponse["Records"]:
			item = AgendaItem()
			item['meetingDate'] = datetime.datetime.utcfromtimestamp(r['meetingDate']/1000).strftime("%Y-%m-%d")
			item['reference'] = r['reference']
			item['agendaItemTitle'] = r['agendaItemTitle']
			item['decisionBodyName'] = r['decisionBodyName']
			item['search_id'] = response.meta['id']
			item['email'] = response.meta['email']
			lg.debug("ITEM: " + pformat(item))
			yield item



	
