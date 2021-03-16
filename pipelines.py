from __future__ import print_function
import configparser


# useful for handling different item types with a single interface
from itemadapter import ItemAdapter

#adapted from https://sodocumentation.net/scrapy/topic/7925/connecting-scrapy-to-mysql
import mysql.connector
from mysql.connector import errorcode
from mysql.connector.constants import ClientFlag


class TmmisSearcherPipeline:
	table = 'searches'
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

	def __init__(self, **kwargs):
		self.cnx = self.mysql_connect()

	def open_spider(self, spider):
		pass

	def process_item(self, item, spider):
		#print("Saving item into db ...")
		#self.save(dict(item))
		#print("Updating item in db ...")
		self.update(dict(item))
		self.sendemail(dict(item))
		return item
	
	def close_spider(self, spider):
		self.mysql_close()
	
	def mysql_connect(self):
		try:
			return mysql.connector.connect(**self.conf)
		except mysql.connector.Error as err:
			if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
				print("Something is wrong with your user name or password")
			elif err.errno == errorcode.ER_BAD_DB_ERROR:
				print("Database does not exist")
			else:
				print(err)
	
	
	def save(self, row): #DEMO CODE NOT WORKING
		cursor = self.cnx.cursor()
		create_query = ("INSERT INTO " + self.table + 
			"(quote, author) "
			"VALUES (%(quote)s, %(author)s)")

		# Insert new row
		cursor.execute(create_query, row)
		lastRecordId = cursor.lastrowid

		# Make sure data is committed to the database
		self.cnx.commit()
		cursor.close()
		if (format(lastRecordId)!="0"):
			print("Item saved with ID: {}" . format(lastRecordId)) 

	def update(self, row): 
		cursor = self.cnx.cursor()
		create_query = ("UPDATE " + self.table + 
			" SET lastran = NOW() WHERE id='" + str(row['search_id']) + "'")
		cursor.execute(create_query, row)
		lastRecordId = cursor.rowcount

		self.cnx.commit()
		cursor.close()
		if (format(lastRecordId)!="0"):
			print("********-----> Item updated with ID: {}" . format(lastRecordId)) 

	def sendemail(self, row):
		print("********-----> sending email: " + str(row['reference']))


	def mysql_close(self):
		self.cnx.close()
