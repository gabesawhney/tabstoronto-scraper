import scrapy
import unicodedata
import datetime
import configparser
import mysql.connector
import os
import logging
from mysql.connector.constants import ClientFlag
from tmmis_searcher.items import AgendaItem
from scrapy import signals
from pydispatch import dispatcher
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from urllib.parse import quote

tabsdebug = 1

class TmmisSearchSpider(scrapy.Spider):

	global tabsdebug
	name = 'tmmis-search'
	allowed_domains = ['app.toronto.ca']
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
			cursor.execute('SELECT searchphrase FROM searches WHERE id = ' + str(id) + ';')
			for row in cursor:
				if row:
					return row[0]
		else:
			pass

	def spider_closed(self, spider):

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

		#let's send emails now
		conn = mysql.connector.connect(**conf)
		conn2 = mysql.connector.connect(**conf)
		cursor = conn.cursor(dictionary=True)
		cursor.execute('SELECT * FROM notifications WHERE emailsent=0 ORDER BY id ASC;')
		logging.info("--------- reviewing notifications")
		emailtext = ""
		lastid = ""
		lastemail = ""
		for row in cursor:
			if emailtext == "":
				if tabsdebug: logging.warning("A: "+str(row['id']))
				emailtext = "<b>Your search for " + self.get_searchphrase(row['id']) + " returned the following new results:</b><br><br>"
			if lastid == "":
				if tabsdebug: logging.warning("B: "+str(row['id'])+" "+row['title'])
				#this is the first record; add to the email we're preparing
				emailtext += row['title'] + ' <a href="http://app.toronto.ca/tmmis/viewAgendaItemHistory.do?item=' + row['reference'] + '">' + row['reference'] + '</a> ' + row['decisionBodyName'] + " " + row['meetingdate'] + "<br><br>"
				lastid = row['id']
				lastemail = row['email']
			elif row['id'] == lastid:
				if tabsdebug: logging.warning("C: "+str(row['id'])+" "+row['title'])
				#this is a subsequent record; add it to the email we're preparing
				emailtext += row['title'] + ' <a href="http://app.toronto.ca/tmmis/viewAgendaItemHistory.do?item=' + row['reference'] + '">' + row['reference'] + '</a> ' + row['decisionBodyName'] + " " + row['meetingdate'] + "<br><br>"
				lastid = row['id']
				lastemail = row['email']
			else:
				if tabsdebug: logging.warning("D: "+str(lastid))
				#this is part of a separate notification, so first let's send the email for the previous one
				emailtext += "<br>To permanently stop receiving notifications for this search, click here: http://pwd.ca/tabs/unsubscribe.php?e=" + quote(lastemail) + "&i=" + str(lastid)
				self.send_email(lastemail,"Tabs Toronto notification: "+self.get_searchphrase(lastid),emailtext)
				logging.info("sent email to "+ lastemail + " for " + str(lastid))

				cursor2 = conn2.cursor()
				if tabsdebug: 
					logging.warning('ABOUT TO RUN: ' + 'UPDATE notifications SET emailsent=1 WHERE id = "' + str(lastid) + '";')
				cursor2.execute('UPDATE notifications SET emailsent=1 WHERE id = "' + str(lastid) + '";')
				conn2.commit()

				if tabsdebug: logging.warning("D2: "+str(row['id']))
				#start preparing the next email
				emailtext = "<b>Your search for " + self.get_searchphrase(row['id']) + " returned the following new results:</b><br><br>"
				emailtext += row['title'] + ' <a href="http://app.toronto.ca/tmmis/viewAgendaItemHistory.do?item=' + row['reference'] + '">' + row['reference'] + '</a> ' + row['decisionBodyName'] + " " + row['meetingdate'] + "<br><br>"
				lastid = row['id']
				lastemail = row['email']

		if lastid == "":
			#there are no emails to send
			pass
		else:
			if tabsdebug: logging.warning("E+")
			if tabsdebug: logging.warning(lastid)
			#send the final email
			emailtext += "<br>To permanently stop receiving notifications for this search, click here: http://pwd.ca/tabs/unsubscribe.php?e=" + quote(lastemail) + "&i=" + str(lastid)
			self.send_email(lastemail,"Tabs Toronto notification: "+self.get_searchphrase(lastid),emailtext)
			logging.info("sent email to "+ lastemail + " for " + str(lastid))

			cursor2 = conn2.cursor()
			if tabsdebug: 
				logging.warning('ABOUT TO RUN: ' + 'UPDATE notifications SET emailsent=1 WHERE id = "' + str(lastid) + '";')
			cursor2.execute('UPDATE notifications SET emailsent=1 WHERE id = "' + str(lastid) + '";')
			conn2.commit()
		logging.info("--------- finished notifications/emails")

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
		cursor.execute('SELECT searchphrase,id,email FROM searches WHERE emailvalidated;')
		rows = cursor.fetchall()

		for row in rows:
			if row:
				fromDate = datetime.date.today() #this will be the 'fromDate' in the search
				toDate = fromDate + datetime.timedelta(days=100) #tihs will be the 'toDate' in the search

				thisurl = 'http://app.toronto.ca/tmmis/findAgendaItem.do?function=doSearch&termId=7&itemsPerPage=100&fromDate=' + fromDate.strftime("%Y-%m-%d") + '&toDate=' + toDate.strftime("%Y-%m-%d") + '&word=' + row[0]
				yield scrapy.Request(thisurl, self.parse, meta=dict(start_url=thisurl,id=row[1],email=row[2]))

		cursor.close()

	def parse(self, response):
		for r in response.css('tr.hoverOver'):
			item = AgendaItem()
			item['meetingDate'] = r.css('td.meetingDate::text').extract_first()
			item['reference'] = r.css('td.reference').css('a::text').extract_first()
			item['agendaItemTitle'] = unicodedata.normalize("NFKD", r.css('td.agendaItemTitle::text').extract_first().strip() )
			item['decisionBodyName'] = unicodedata.normalize("NFKD", r.css('td.decisionBodyName::text').extract_first().strip() )
			#item['start_url'] = response.meta['start_url']
			item['search_id'] = response.meta['id']
			item['email'] = response.meta['email']
			yield item

	
