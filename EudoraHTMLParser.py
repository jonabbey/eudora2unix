import os
import re
from HTMLParser import HTMLParser, HTMLParseError

class EudoraHTMLParser(HTMLParser):

	def __init__(self):
		HTMLParser.__init__(self)
		self.cids = []

	def handle_starttag(self, tag, attrs):
		if tag == "img":
			for k, v in attrs:
				if k == 'src':
					if v.startswith('cid:'):
						self.cids.append(v)
					else:
						if not v.startswith('http://') and not v.startswith('https://'):
							self.cids.append(v)
					
	def handle_endtag(self, tag):
		pass

	def get_cids(self):
		return self.cids


