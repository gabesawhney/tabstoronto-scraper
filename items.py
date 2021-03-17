# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy

class AgendaItem(scrapy.Item):
    agendaItemTitle = scrapy.Field()
    reference = scrapy.Field()
    meetingDate = scrapy.Field()
    decisionBodyName = scrapy.Field()

    search_id = scrapy.Field()
    email = scrapy.Field()