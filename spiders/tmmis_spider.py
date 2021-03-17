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
		for row in cursor:
			if row:
				if lastid == "" or row['id'] == lastid:
					emailtext += row['title'] + " " + row['reference'] + " " + row['meetingdate'] + row['decisionBodyName']
					
					lastid = row['id']
				else:
					#send that last email
					print("send an email to " + row['email'] + "with the text:")
					print(emailtext)

					#INSERT SENDING CODE HERE

					cursor2 = conn2.cursor()
					print('ABOUT TO RUN: ' + 'UPDATE notifications SET emailsent=1 WHERE id = "' + str(row['id']) + '";')
					cursor2.execute('UPDATE notifications SET emailsent=1 WHERE id = "' + str(row['id']) + '";')

					#prepare the next email
					emailtext = row['title'] + " " + row['reference'] + " " + row['meetingdate'] + row['decisionBodyName']
					lastid = row['id']

		#send the final email
		print("send an email to " + row['email'] + " with the text: ")
		print(emailtext)
#		self.send_email(to="gabe@pwd.ca",subject="blah",content=emailtext)
		self.send_email(subject="blah",content=emailtext)

		cursor2 = conn2.cursor()
		print('ABOUT TO RUN: ' + 'UPDATE notifications SET emailsent=1 WHERE id = "' + str(row['id']) + '";')
		cursor2.execute('UPDATE notifications SET emailsent=1 WHERE id = "' + str(row['id']) + '";')


	def send_email(to,subject,content):
		message = Mail(
    		from_email='gabe@pwd.ca',
#   			to_emails=to,
   			to_emails='gabe@pwd.ca',
    		subject='Sending with Twilio SendGrid is Fun',
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
