import scrapy
import unicodedata
import datetime
import configparser
import mysql.connector
from mysql.connector.constants import ClientFlag
from tmmis_searcher.items import AgendaItem


class TmmisSearchSpider(scrapy.Spider):

	name = 'tmmis-search'
	allowed_domains = ['app.toronto.ca']

	def start_requests(self):
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
		conn = mysql.connector.connect(**conf)
		cursor = conn.cursor()
		cursor.execute('SELECT searchphrase,id FROM searches WHERE emailvalidated;')
		rows = cursor.fetchall()

		for row in rows:
			if row:

				today = datetime.date.today()
				insevendays = today + datetime.timedelta(days=7)
				#print("the date for one week from now: " + insevendays.strftime("%Y-%m-%d"))

				thisurl = 'http://app.toronto.ca/tmmis/findAgendaItem.do?function=doSearch&termId=7&fromDate=' + today.strftime("%Y-%m-%d") + '&toDate=' + insevendays.strftime("%Y-%m-%d") + '&word=' + row[0]
				yield scrapy.Request(thisurl, self.parse, meta=dict(start_url=thisurl,id=row[1]))
				#this might be where we send the email

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
			yield item
