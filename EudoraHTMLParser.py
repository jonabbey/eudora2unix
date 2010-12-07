import os
from HTMLParser import HTMLParser

class EudoraHTMLParser(HTMLParser):

	self.cids = []

	def handle_starttag(self, tag, attrs):
		if tag == "img":
			for k, v in attrs:
				if k == 'src' and v.startswith('cid:'):
					self.cids.append(v[4:])
					
	def handle_endtag(self, tag):
		pass

	def get_reset_cids(self):
		retr = self.cids
		self.cids = []
		return self.cids

