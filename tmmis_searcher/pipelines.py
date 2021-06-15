from __future__ import print_function
import configparser
import os
import logging


# useful for handling different item types with a single interface
from itemadapter import ItemAdapter

#adapted from https://sodocumentation.net/scrapy/topic/7925/connecting-scrapy-to-mysql
import mysql.connector
from mysql.connector import errorcode
from mysql.connector.constants import ClientFlag

tabsdebug = 1

class TmmisSearcherPipeline:
	global tabsdebug

	def __init__(self, **kwargs):
		#self.cnx = self.mysql_connect()
		pass

	def open_spider(self, spider):
		self.cnx = self.mysql_connect(spider)

	def process_item(self, item, spider):
		self.update(dict(item))
		return item
	
	def close_spider(self, spider):
		self.mysql_close()
	
	def mysql_connect(self, spider):

		if spider.settings.get('MYSQL_USER'):
			self.conf = {
				'user': spider.settings.get('MYSQL_USER'),
				'password': spider.settings.get('MYSQL_PASSWORD'),
				'host': spider.settings.get('MYSQL_HOST'),
				'database': spider.settings.get('MYSQL_DATABASE'),
			 	'raise_on_warnings': True
			}
		else:
			raise Exception('mysql config failure')	

		try:
			return mysql.connector.connect(**self.conf)
		except mysql.connector.Error as err:
			if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
				print("Something is wrong with your user name or password")
			elif err.errno == errorcode.ER_BAD_DB_ERROR:
				print("Database does not exist")
			else:
				print(err)
	
	def update(self, row): 
		cursor = self.cnx.cursor()
		rec = row
		create_query = ("INSERT INTO notifications " +
			"(id, title, reference, meetingdate, decisionBodyName, email) "
			"VALUES (%s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE id=id")

		# Insert new row
		data = (rec['search_id'], rec['agendaItemTitle'], rec['reference'], rec['meetingDate'], rec['decisionBodyName'], rec['email'])
		cursor.execute(create_query, data)
		if tabsdebug and cursor.rowcount > 0:
			logging.info('JUST RAN ('+str(cursor.rowcount)+'): ' + cursor.statement)
		lastRecordId = cursor.lastrowid

		# Make sure data is committed to the database
		self.cnx.commit()
		cursor.close()

	def mysql_close(self):
		self.cnx.close()
