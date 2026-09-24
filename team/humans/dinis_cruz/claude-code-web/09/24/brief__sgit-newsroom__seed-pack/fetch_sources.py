#!/usr/bin/env python3
"""Snapshot every site in the sgit network as text, for the newsroom to read.

    python3 tools/fetch_sources.py                 # all sites in SITES, into sources/sites/
    python3 tools/fetch_sources.py riskmandate.ai  # one site

For each site it fetches /llms.txt and /llms-full.txt, then every same-site .md page that llms.txt
links to, and /versions.md with every release note it links to, where a site keeps one. Nothing else: no HTML scraping, no images. Every file is recorded in
sources/sites/manifest.json with its URL, the time it was fetched, its size and its sha256, so
tomorrow's run can tell exactly what changed. Standard library only.
"""
import hashlib, json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SITES = ['sgit.ai', 'riskmandate.ai', 'graphs.sgit.ai', 'risks.sgit.ai', 'standards.sgit.ai', 'twins.sgit.ai',
         'newsroom.sgit.ai', 'pt.newsroom.sgit.ai', 'abp.sgit.ai', 'store.sgit.ai', 'llms.sgit.ai', 'open-source.sgit.ai',
         'subscriptions.sgit.ai', 'wardley-maps.sgit.ai', 'sg-compute.sgit.ai', 'providers.sgit.ai', 'skills.sgit.ai',
         'nhi.sgit.ai', 'nfrs.sgit.ai', 'issues-fs.sgit.ai', 'coding.sgit.ai', 'chrome-extensions.sgit.ai', 'games.sgit.ai',
         'influences.sgit.ai', 'infographics.sgit.ai', 'pki.sgit.ai', 'sg-sentinel.sgit.ai', 'teams.sgit.ai',
         'threat-modeling.sgit.ai', 'docs.diniscruz.ai']
OUT = 'sources/sites'
MAX_PAGES = 600
MAX_BYTES = 8_000_000


class Fetcher:

    def __init__(self):
        self.manifest = {}
        path = os.path.join(OUT, 'manifest.json')
        if os.path.exists(path):
            self.manifest = json.load(open(path))

    def get(self, url):
        try:
            r = urlopen(Request(url, headers={'User-Agent': 'sgit-newsroom/0.1 (+https://sgit.ai)'}), timeout=30)
            body = r.read(MAX_BYTES + 1)
            if r.status != 200 or len(body) > MAX_BYTES:
                return None
            head = body[:300].lstrip().lower()
            if head.startswith(b'<!doctype html') or head.startswith(b'<html'):
                return None                                   # a 404 page served as 200, or not text
            return body
        except Exception:
            return None

    def save(self, host, url, body):
        path = urlparse(url).path.lstrip('/') or 'index.md'
        local = os.path.join(OUT, host, path)
        os.makedirs(os.path.dirname(local), exist_ok=True)
        open(local, 'wb').write(body)
        self.manifest[url] = {'site': host, 'file': os.path.relpath(local, 'sources'), 'bytes': len(body),
                              'sha256': hashlib.sha256(body).hexdigest(),
                              'fetched': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}

    def site(self, host):
        base = f'https://{host}'
        got = 0
        llms = self.get(base + '/llms.txt')
        for name, body in [('/llms.txt', llms), ('/llms-full.txt', self.get(base + '/llms-full.txt'))]:
            if body:
                self.save(host, base + name, body); got += 1
        if not llms:
            return host, got
        text = llms.decode('utf-8', 'replace')
        versions = self.get(base + '/versions.md')            # a site's version record, where it keeps one
        if versions:
            self.save(host, base + '/versions.md', versions); got += 1
            text += '\n' + re.sub(r'(https?://\S+?\.md)', r'(\1)', versions.decode('utf-8', 'replace'))
        links = re.findall(r'\((https?://[^)\s]+\.md|/[^)\s]+\.md|[a-z0-9][^)\s:]*\.md)\)', text)
        urls = []
        for l in links:
            u = l if l.startswith('http') else base + '/' + l.lstrip('/')
            if urlparse(u).hostname == host and u not in urls:
                urls.append(u)
        with ThreadPoolExecutor(8) as ex:
            for u, body in zip(urls[:MAX_PAGES], ex.map(self.get, urls[:MAX_PAGES])):
                if body:
                    self.save(host, u, body); got += 1
        return host, got

    def run(self, hosts):
        with ThreadPoolExecutor(6) as ex:
            for host, n in ex.map(self.site, hosts):
                print(f'{host:32} {n:4} files')
        os.makedirs(OUT, exist_ok=True)
        json.dump(dict(sorted(self.manifest.items())), open(os.path.join(OUT, 'manifest.json'), 'w'), indent=1)


if __name__ == '__main__':
    Fetcher().run(sys.argv[1:] or SITES)
