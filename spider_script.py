
import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.spiders import CrawlSpider, Rule
from scrapy.linkextractors import LinkExtractor

class SEOSitemapSpider(CrawlSpider):
    name = 'seo_spider'
    allowed_domains = ['vagelos.columbia.edu']
    start_urls = ['https://vagelos.columbia.edu']
    
    rules = (
        Rule(
            LinkExtractor(
                deny_extensions=['7z', 'gz', 'txt', 'zip', 'csv', 'pdf', 'docx', 'xlsx', 'tar', 'png', 'jpg', 'jpeg', 'gif', 'svg', 'css', 'js'],
                deny=[r'/file/\d+/download']
            ),
            callback='parse_item',
            follow=True
        ),
    )

    custom_settings = {
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'ROBOTSTXT_OBEY': False,
        'DOWNLOAD_MAXSIZE': 5242880,
        'LOG_LEVEL': 'INFO',
        'CLOSESPIDER_PAGECOUNT': 210,
        # Breadth-first crawling: process shallower pages before deeper ones
        'DEPTH_PRIORITY': 1,
        'SCHEDULER_DISK_QUEUE': 'scrapy.squeues.PickleFifoDiskQueue',
        'SCHEDULER_MEMORY_QUEUE': 'scrapy.squeues.FifoMemoryQueue',
        'FEEDS': {
            'crawl_output.jsonl': {'format': 'jsonlines', 'overwrite': True}
        }
    }

    def parse_item(self, response):
        yield {
            'url': response.url,
            'status': response.status,
            'title': response.css('title::text').get(default='').strip(),
            'h1': response.css('h1::text').get(default='').strip(),
            'meta_desc': response.xpath("//meta[@name='description']/@content").get(default='').strip(),
            'word_count': len(response.xpath('//body//text()').getall())
        }

if __name__ == "__main__":
    process = CrawlerProcess()
    process.crawl(SEOSitemapSpider)
    process.start()
