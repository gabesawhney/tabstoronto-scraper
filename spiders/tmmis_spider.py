import scrapy
import unicodedata
import datetime
import configparser
import mysql.connector
import os
from mysql.connector.constants import ClientFlag
from tmmis_searcher.items import AgendaItem
from scrapy import signals
from pydispatch import dispatcher
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from urllib.parse import quote

configfile = configparser.ConfigParser()
configfile.read('mysql-config.ini')
conf = {
	'user': configfile['DEFAULT']['user'],
	'password': configfile['DEFAULT']['password'],
	'host': configfile['DEFAULT']['host'],
	'database': configfile['DEFAULT']['database'],
	'client_flags': [ClientFlag.SSL],
		'ssl_ca': 'ssl/server-ca.pem',
		'ssl_cert': 'ssl/client-cert.pem',
		'ssl_key': 'ssl/client-key.pem',
		'raise_on_warnings': True
		
}

def get_searchphrase(id):
		conn = mysql.connector.connect(**conf)
		cursor = conn.cursor()
		print("****" + str(id))
		if str(id) != "":
			cursor.execute('SELECT searchphrase FROM searches WHERE id = ' + str(id) + ';')
			#rows = cursor.fetchall()
			for row in cursor:
				if row:
					#print(row[0])
					return row[0]
		else:
			print("PROBLEM AAA")

class TmmisSearchSpider(scrapy.Spider):

	name = 'tmmis-search'
	allowed_domains = ['app.toronto.ca']

	def __init__(self):
		dispatcher.connect(self.spider_closed, signals.spider_closed)

	def spider_closed(self, spider):
		#let's send emails now
		conn = mysql.connector.connect(**conf)
		conn2 = mysql.connector.connect(**conf)
		cursor = conn.cursor(dictionary=True)
		cursor.execute('SELECT * FROM notifications WHERE emailsent=0;')
		#rows = cursor.fetchall()
		emailtext = ""
		lastid = ""
		lastemail = ""
		for row in cursor:
			if row:
				if emailtext == "":
					emailtext = "Your search for " + get_searchphrase(row['id']) + " returned the following new results:\n\n"
				if lastid == "":
					#this is the first record; add to the email we're preparing
					emailtext += row['title'] + " " + row['reference'] + " " + row['meetingdate'] + " " + row['decisionBodyName'] + "\n"
					lastid = row['id']
					lastemail = row['email']
				elif row['id'] == lastid:
					#this is a subsequent record; add it to the email we're preparing
					emailtext += row['title'] + " " + row['reference'] + " " + row['meetingdate'] + " " + row['decisionBodyName'] + "\n"
					lastid = row['id']
					lastemail = row['email']
				else:
					#this is part of a separate notification, so first let's send the email for the previous one
					emailtext += "To permanently stop receiving notifications for this search, click here: http://pwd.ca/tabs/unsubscribe.php?e=" + quote(row['email']) + "&i=" + str(lastid)
					self.send_email(row['email'],"Tabs Toronto notification: "+get_searchphrase(lastid),emailtext)

					cursor2 = conn2.cursor()
					print('ABOUT TO RUN: ' + 'UPDATE notifications SET emailsent=1 WHERE id = "' + str(row['id']) + '";')
					cursor2.execute('UPDATE notifications SET emailsent=1 WHERE id = "' + str(row['id']) + '";')
					conn2.commit()

					#start preparing the next email
					emailtext = "Your search for " + get_searchphrase(row['id']) + " returned the following new results:\n\n"
					emailtext += row['title'] + " " + row['reference'] + " " + row['meetingdate'] + " " + row['decisionBodyName'] + "\n"
					lastid = row['id']
					lastemail = row['email']

		if lastid == "":
			#there are no emails to send
			lastid = ""
		else:
			#send the final email
			emailtext += "To permanently stop receiving notifications for this search, click here: http://pwd.ca/tabs/unsubscribe.php?e=" + quote(lastemail) + "&i=" + str(lastid)
			print("zzz")
			self.send_email(lastemail,"Tabs Toronto notification: "+get_searchphrase(lastid),emailtext)

			cursor2 = conn2.cursor()
			print('ABOUT TO RUN: ' + 'UPDATE notifications SET emailsent=1 WHERE id = "' + str(row['id']) + '";')
			cursor2.execute('UPDATE notifications SET emailsent=1 WHERE id = "' + str(row['id']) + '";')
			conn2.commit()

	def send_email(self,to,subject,content):
		message = Mail(
    		from_email='gabe@pwd.ca',
#   			to_emails=to,
   			to_emails=to,
    		subject=subject,
    		html_content=content)
		try:
			sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
			response = sg.send(message)
			print(response.status_code)
			print(response.body)
			print(response.headers)
		except Exception as e:
			print(e.message)

	def start_requests(self):
		conn = mysql.connector.connect(**conf)
		cursor = conn.cursor()
		cursor.execute('SELECT searchphrase,id,email FROM searches WHERE emailvalidated;')
		rows = cursor.fetchall()

		for row in rows:
			if row:
				today = datetime.date.today()
				insevendays = today + datetime.timedelta(days=7)
				#print("the date for one week from now: " + insevendays.strftime("%Y-%m-%d"))

				thisurl = 'http://app.toronto.ca/tmmis/findAgendaItem.do?function=doSearch&termId=7&fromDate=' + today.strftime("%Y-%m-%d") + '&toDate=' + insevendays.strftime("%Y-%m-%d") + '&word=' + row[0]
				yield scrapy.Request(thisurl, self.parse, meta=dict(start_url=thisurl,id=row[1],email=row[2]))
				#SEND EMAIL
				#hey, $row[2], your search for "$row[0]" matched some stuff

				#print("here's one: " + thisurl,row[1],row[2])

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

	
