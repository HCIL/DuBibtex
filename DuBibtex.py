# DuBibtex
# This script merges duplicated bibtex items from a list of .bib files, capitalize the titles,
# and more importantly, resolve missing DOIs, years.
# This script assumes the first line of each bibtex item contains its bib iD.
# This is typically true if the bibtex item is from Google Scholar or DBLP.
# Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)
# Reference: http://www.bibtex.org/Format/
# Sources of DOI: Google, ACM, IEEE, Springer, Caltech, Wiley
import re, requests, json, configparser

__author__ = "Ruofei Du"


class Paras:
    section = "DuBibtex"
    searchDOI = True
    inputFileList = []
    outputFile = ""
    useOfflineDOI = False
    printSelfInfo = True
    keepComments = False
    debugBibCrawler = True
    debugStatistics = True
    doiJsonFile = ""
    minYear = 1946
    timeOut = 3
    header = {}
    DOI2URL = False
    fieldRemovalList = []


def request_url(url):
    return requests.get(url, headers=Paras.header).text


class Re:
    bib = re.compile('\s*\@(\w+)\{([\w\d\.]+),')
    item = re.compile('\s*(\w+)\s*=\s*[\{"]\s*(.*)\s*[\}"]')
    item2 = re.compile('\s*(\w+)\s*=\s*[\{"]\{\s*(.*)\s*[\}"]\}')
    endl = re.compile('\s*}\s*')
    doiJson = re.compile('doi\.org\\?\/([\w\d\.\\\/]*)', flags=re.MULTILINE)
    doiUrl = re.compile('doi\.org\/([\w\d\.\\\/]*)', flags=re.MULTILINE)
    doiJavascript = re.compile('doi\"\:\"([\w\d\.\\\/]*)\"', flags=re.MULTILINE)
    doiText = re.compile('"DOI":"([\w\.\\\/]*)"', flags=re.MULTILINE)
    doiSpringer = re.compile('chapter\/([\w\.\\\/\_\-]*)', flags=re.MULTILINE)
    doiWiley = re.compile('doi\/abs\/([\w\.\\\/\_\-]*)', flags=re.MULTILINE)
    doiCaltech = re.compile('authors\.library\.caltech\.edu\/(\d+)', flags=re.MULTILINE)
    doiPubmed = re.compile('nlm\.nih\.gov\/pubmed\/(\d+)', flags=re.MULTILINE)
    urlArxiv = re.compile('arxiv\.org\/pdf\/([\d\.]+)', flags=re.MULTILINE)
    acm = re.compile('citation\.cfm\?id\=([\d\.]+)', flags=re.MULTILINE)
    acmBib = re.compile('<PRE id="[\d\.]+">(.+)<\/pre>', flags=re.MULTILINE | re.IGNORECASE | re.S)
    ieee = re.compile('ieee\.org\/document\/(\d+)', flags=re.MULTILINE)
    year = re.compile('\w+(\d+)')


class Parser:
    fout = None
    bibDict = {}
    doiDict = {}
    duplicated = False
    numMissing, numDuplicated, numFixed = 0, 0, 0
    # current bibitem and bib ID
    cur, bib = None, ''

    def __init__(self):
        config = configparser.ConfigParser()
        config.read("config.ini")
        Paras.header['User-Agent'] = config.get(Paras.section, "header").strip()
        Paras.searchDOI = config.getboolean(Paras.section, "searchDOI")
        Paras.useOfflineDOI = config.getboolean(Paras.section, "useOfflineDOI")
        Paras.printSelfInfo = config.getboolean(Paras.section, "printSelfInfo")
        Paras.keepComments = config.getboolean(Paras.section, "keepComments")
        Paras.debugBibCrawler = config.getboolean(Paras.section, "debugBibCrawler")
        Paras.debugStatistics = config.getboolean(Paras.section, "debugStatistics")
        Paras.inputFileList = config.get(Paras.section, "inputFileList").strip().split(",")
        Paras.doiJsonFile = config.get(Paras.section, "doiJsonFile").strip()
        Paras.outputFile = config.get(Paras.section, "outputFile").strip()
        Paras.fieldRemovalList = config.get(Paras.section, "fieldRemoval").strip().split(",")
        Paras.minYear = config.getint(Paras.section, "minYear")
        Paras.timeOut = config.getint(Paras.section, "timeOut")
        Paras.DOI2URL = config.getint(Paras.section, "DOI2URL")

        self.fout = open(Paras.outputFile, 'w')
        if Paras.printSelfInfo:
            self.fout.write('% Automatically generated by DuBibTeX.\n% https://github.com/ruofeidu/DuBibtex\n')
        if Paras.useOfflineDOI:
            with open(Paras.doiJsonFile) as f:
                self.doiDict = json.load(f)

    def clear(self):
        self.duplicated = False
        self.bib = ''

    def debug_bib(self, s):
        if not Paras.debugBibCrawler:
            return
        print(s)

    def fix_doi(self, _doi):
        if Paras.debugStatistics:
            self.numMissing += 1
            self.numFixed += 1
        self.cur['doi'] = _doi
        if Paras.DOI2URL:
            self.cur['url'] = 'http://doi.org/%s' % _doi

    def write_current_item(self):
        self.fout.write('@%s{%s,\n' % (self.cur['type'], self.bib))

        if 'year' not in self.cur or len(self.cur['year']) < 4:
            m = Re.year.search(self.bib)
            if m and m.groups():
                self.cur['year'] = m.groups()[0]

        if self.bib in self.doiDict:
            self.debug_bib('Missing DOI, but obtained from the local dict JSON.')
            self.fix_doi(self.doiDict[self.bib])

        if Paras.searchDOI and int(self.cur['year']) > Paras.minYear and 'doi' not in self.cur \
                and self.cur['type'].lower() not in ['misc', 'book']:
            # search for DOI
            self.debug_bib('Missing DOI, search "%s"...' % self.cur['title'])

            if 'journal' in self.cur and self.cur['journal'][:5].lower() == 'arxiv':
                content = request_url('https://www.google.com/search?q=%s' % self.cur['title'])
                m = Re.urlArxiv.search(content)
                if m and len(m.groups()) > 0:
                    self.cur['url'] = "https://arxiv.org/pdf/%s" % m.groups()[0]
                    self.debug_bib('Missing DOI, search "%s"...' % self.cur['title'])
            else:
                d = google_lookup(self.cur['title'], self)
                if not d:
                    d = crossref_lookup(self.cur['title'])
                if d:
                    self.fix_doi(d)
                else:
                    self.numMissing += 1

        if 'doi' in self.cur:
            self.cur['doi'] = fix_underscore(self.cur['doi'])
            self.doiDict[self.bib] = self.cur['doi']

        del self.cur['type']
        n = len(self.cur.keys())
        for i, key in enumerate(self.cur.keys()):
            if key in Paras.fieldRemovalList:
                continue
            if key in ['booktitle', 'journal', 'title']:
                self.cur[key] = capitalize(self.cur[key])
                # print(cur[key])

            if key in ['title']:
                self.fout.write('  %s={{%s}}' % (key, self.cur[key]))
            else:
                self.fout.write('  %s={%s}' % (key, self.cur[key]))

            if i != n - 1:
                self.fout.write(',')
            self.fout.write('\n')
        self.fout.write('}\n\n')

    def add_new_bib(self, bib_id, bib_type):
        self.bib = bib_id
        if self.bib in self.bibDict:
            self.duplicated = True
            return
        self.bibDict[self.bib] = {}
        self.cur = self.bibDict[self.bib]
        self.cur['type'] = bib_type

    def parse_line(self, line):
        # match EOF
        if Re.endl.match(line):
            if not self.duplicated:
                self.write_current_item()
            self.clear()
            return

        # match duplicates
        if self.duplicated:
            if Paras.debugStatistics:
                print("* duplicated %s" % self.bib)
                self.numDuplicated += 1
            return

        # match new bib item
        m = Re.bib.match(line)
        if m and len(m.groups()) > 0:
            self.add_new_bib(m.groups()[1], m.groups()[0])

        # output comments
        if not self.bib:
            if Paras.keepComments:
                self.fout.write(line)
            return

        # for each bibtex, first match {{}} or {""}, then match {} or ""
        m = Re.item2.match(line)
        if not m:
            m = Re.item.match(line)
        if m and len(m.groups()) > 0:
            self.cur[m.groups()[0]] = m.groups()[1]

    def print_statistics(self):
        print("%d missing doi, %d fixed, %d duplicated" % (self.numMissing, self.numFixed, self.numDuplicated))

    def shut_down(self):
        self.fout.close()
        if Paras.useOfflineDOI:
            with open(Paras.doiJsonFile, 'w') as outfile:
                json.dump(self.doiDict, outfile)
                print("DuBibTeX has saved known DOI to %s." % Paras.doiJsonFile)
        self.print_statistics()


def crossref_lookup(_title):
    content = request_url('https://api.crossref.org/works?rows=5&query.title=%s' % _title)
    m = Re.doiJson.search(content)
    if m and len(m.groups()) > 0:
        res = m.groups()[0]
        res = res.replace('\\', '')
        if Paras.debugBibCrawler:
            print("DOI from CrossRef Lookup: %s\n" % res)
        return res
    return None


def levenshtein(s1, s2):
    s1 = s1.lower()
    s2 = s2.lower()
    if len(s1) < len(s2):
        return levenshtein(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def google_lookup(s, parser):
    html = request_url('https://www.google.com/search?q=%s' % s)

    m = Re.acm.search(html)
    if m and len(m.groups()) > 0:
        content_acm = request_url('https://dl.acm.org/exportformats.cfm?id=%s&expformat=bibtex' % m.groups()[0])
        m = Re.acmBib.search(content_acm, re.M)
        # TODO: month
        if m and len(m.groups()) > 0:
            acm_lines = m.groups()[0].splitlines()
            res = ''
            for l in acm_lines:
                if len(l) < 3 or l[0] == '@' or l[0] == '}':
                    continue
                mm = Re.item.search(l)
                old_cur = parser.cur.copy()
                if mm and len(mm.groups()) > 0:
                    cur_left, cur_right = mm.groups()[0].strip(), mm.groups()[1].strip()
                    if cur_left == 'doi':
                        res = cur_right
                    if cur_left in ['class', 'href', 'doi', 'numpages']:
                        continue
                    parser.cur[cur_left] = cur_right

            dist = levenshtein(old_cur['title'], parser.cur['title'])
            print(dist, old_cur['title'], parser.cur['title'])
            if dist > 2:
                parser.cur = old_cur
                res = ''

            if res:
                if Paras.debugBibCrawler:
                    print("DOI from Google and ACM BibTeX: %s\n" % res)
                return res

    m = Re.doiSpringer.search(html)
    if m and len(m.groups()) > 0:
        res = m.groups()[0].replace('\\', '')
        print("DOI from Google and Springer: %s\n" % res)
        return res

    m = Re.doiWiley.search(html)
    if m and len(m.groups()) > 0:
        res = m.groups()[0].replace('\\', '')
        print("DOI from Google and Wiley: %s\n" % res)
        return res

    m = Re.doiUrl.search(html, re.M)
    if m and len(m.groups()) > 0:
        res = m.groups()[0]
        if Paras.debugBibCrawler:
            print("DOI from Google and DOI.org: %s\n" % res)
        return res

    m = Re.ieee.search(html)
    if m and len(m.groups()) > 0:
        html_ieee = request_url('https://ieeexplore.ieee.org/document/%s' % m.groups()[0])
        m = Re.doiJavascript.search(html_ieee, re.M)
        if m and len(m.groups()) > 0:
            res = m.groups()[0].replace('\\', '')
            print("DOI from Google and IEEE: %s\n" % res)
            return res

    m = Re.doiCaltech.search(html)
    if m and len(m.groups()) > 0:
        html_cal = request_url('https://authors.library.caltech.edu/%s' % m.groups()[0])
        m = Re.doiUrl.search(html_cal, re.M)
        if m and len(m.groups()) > 0:
            res = m.groups()[0]
            res = res.replace('\\', '')
            print("DOI from Google and Caltech: %s\n" % res)
            return res

    m = Re.doiPubmed.search(html)
    if m and len(m.groups()) > 0:
        html_pubmed = request_url('https://www.ncbi.nlm.nih.gov/pubmed/%s' % m.groups()[0])
        m = Re.doiUrl.search(html_pubmed, re.M)
        if m and len(m.groups()) > 0:
            res = m.groups()[0]
            res = res.replace('\\', '')
            print("DOI from Google and PubMed: %s\n" % res)
            return res
    print("* Nothing was found.\n")
    return None


def fix_underscore(s):
    return re.sub('[^\_]\_', '\\\_', s)


def capitalize(s, spliter=' '):
    lower_cases = {'a', 'an', 'the', 'to', 'on', 'in', 'of', 'at', 'by', 'for', 'or', 'and', 'vs.', 'iOS'}

    s = s.strip(',.- ')
    # reverse IEEE conferences
    if s.rfind(',') > 0 and s[-3:].lower() == ' on':
        p = s.rfind(',')
        s = s[p + 2:] + s[:p]

    words = s.split(spliter)
    capitalized_words = []
    for i, word in enumerate(words):
        if len(word) == 0:
            continue
        if 0 < i < len(words) - 1 and word.lower() in lower_cases:
            capitalized_words.append(word.lower())
        else:
            capitalized_words.append(word[0].upper() + word[1:])
    s = spliter.join(capitalized_words)

    return s if spliter == '-' else capitalize(s, '-')


if __name__ == "__main__":
    p = Parser()

    for filename in Paras.inputFileList:
        with open(filename, 'r') as f:
            lines = f.readlines()
            for line in lines:
                p.parse_line(line)

    p.shut_down()
