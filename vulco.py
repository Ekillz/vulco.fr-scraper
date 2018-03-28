# -*- coding: utf-8 -*-
import scrapy
from lxml import etree
from scrapy.selector import Selector
from cloudant.client import Cloudant
from datetime import datetime
from urlparse import urlparse
import re

class VulcoSpider(scrapy.Spider):
    name = "vulco"
    allowed_domains = ["vulco.fr"]
    
    start_urls = ["http://vulco.fr/centres-auto"]

    client = Cloudant()

    # Connect to the server
    client.connect()

    # Perform client tasks...
    session = client.session()

    def parse(self, response):
        links = response.xpath('//*[@class="departmentListing"]/ul/li/a/@href').extract()
        for link in links:
            yield scrapy.Request(url=link, callback=self.parse_results)

    def parse_results(self, response):
        links = response.xpath('//*[@id="sl-results"]/ol/li/article/footer/a/@href').extract()
        for link in links:
            yield scrapy.Request(url='http://vulco.fr'+link, callback=self.parse_page)

    def parse_page(self, response):
        poiDB = self.client["poi_test"]
        
        splitUrl = response.url.split('-')

        aeId = 'vulco/'+(splitUrl[len(splitUrl)-1])
        curDate = datetime.utcnow().isoformat()

        # Get remote doc if exists
        try:
            doc = poiDB[aeId]
        except KeyError:
            doc = {
                '_id': aeId,
                'created_date': curDate,
                'last_update': curDate,
                'comments': "",
                'infos': {},
                'contacts': {
                    'telephones': [],
                    'emails': [],
                    'websites': []
                }

            }

        doc = self.extract_Infos(doc, response)
        doc = self.extract_Services(doc, response)

        doc['contacts']['websites'] = doc['contacts']['websites']+[response.url]

        if '_rev' in doc:
            newPOI = doc.save()
        else:
            newPOI = poiDB.create_document(doc)

        print(doc)

    def extract_Infos(self, doc, item):
        doc['name'] = item.xpath('//h1/text()').extract_first()

        manager = item.xpath('//*[@class="dm-left"]/h3/text()').extract_first().replace('Directeur du centre : ','').encode('utf-8')
        doc['infos']['manager'] = manager
        
        address = item.xpath('//*[@class="dm-left"]/address/text()').extract()

        doc['addresses'] = [{'primary':True}]
        doc['addresses'][0]['l1'] = address[0].strip().encode('utf-8')
        doc['addresses'][0]['city'] = address[1].strip().encode('utf-8').strip()
        doc['addresses'][0]['zip'] = item.xpath('//*[@class="dm-left"]/address/a/text()').extract_first().strip().encode('utf-8')

        email = item.xpath('//*[@class="sl-mail"]/text()').extract()
        doc['contacts']['emails'] = [str(email[0]) + "@" + str(email[1])]

        doc['infos']['opening_hours'] = "" 
        for property in item.xpath('//*[@class="vulco-hours-component"]/dl/*/text()').extract():
            doc['infos']['opening_hours'] = doc['infos']['opening_hours'] + " " + property.strip().encode('utf-8')
        doc['infos']['opening_hours'] = doc['infos']['opening_hours'].strip()

        phone = item.xpath('//*[@class="vulco-contact-component"]/li[1]/text()').extract_first().encode('utf-8')
        doc['contacts']['telephones'] = doc['contacts']['telephones']+[{
                'type': 'voice',
                'local_number': phone.replace(' ','').strip(),
                'intl_number': '+33'+(phone.replace('0','',1).replace(' ','').strip())
                }]

        return doc

    def extract_Services(self, doc, item):
        services = []
        
        for property in item.xpath('//*[@class="dealer-tabs"]/div/ul[2]/li[2]/div/article/div/ul/li/text()').extract():
            services = services + ["PNEUMATIQUES "+property.encode('utf-8').strip()]

        for property in item.xpath('//*[@class="dealer-tabs"]/div/ul[2]/li[2]/div/article/a/text()').extract():
            services = services + [property.encode('utf-8').strip()]
        
        # Remove doubles 
        doc['services'] = list(set(services))

        return doc