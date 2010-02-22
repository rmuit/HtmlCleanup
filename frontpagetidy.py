#!/usr/bin/python

# Read old MS FrontPage HTML document and tidy it up.
# Contains site specific functions, so the script will need to be changed somewhat
# for every site.
# Version: 20100217/ipce.info

from optparse import OptionParser
import re
from BeautifulSoup import BeautifulSoup, Tag, NavigableString, Comment

c_common_font = 'Book Antiqua, Times New Roman, Times'
c_img_bullet_re = 'expbul.?.?\.gif$'

# We have no options as yet, but still this is a convenient way of printing usage
#usage = "usage: %prog [options] arg1 arg2"
a = OptionParser(usage = "usage: %prog htmlfile",
                 description = "filename should be a HTML file")
(options, args) = a.parse_args()
if len(args) != 1:
  print "Number of command line arguments must be 1!"
  a.print_help()
  exit()

### Function definitions

# move all contents out of one tag, to just before the other tag
def movecontentsbefore(fromwithin, tobefore):
  movecontentsinside(fromwithin, tobefore.parent, tobefore.indexInParent())

def movecontentsinside(fromwithin, toinside, startindex=0):
  r = fromwithin.contents
  i = startindex
  while len(r):
    toinside.insert(i, r[0])
    i = i + 1

### THIS REGEX IS REFERENCED AS A 'GLOBAL' INSIDE FUNCTIONS
#
rx = re.compile('^(?:\s|\&nbsp\;|\<br \/\>)+$')
rxe = re.compile('(?:\s|\&nbsp\;|\<br \/\>)+$')
#NB: the \n and ' ' are probably not necessary here because they do not affect the 
# rendering of the document (and taking the '\n' away as we are doing now may
# be worse for readability of the source?) ...
# ...but I'll leave it in anyway, until I'm sure. Things work now, anyway.
#NB2: above is not really correct. They should be in the regexp
# because strings can be compound, like '\r\n        &nbsp;&nbsp;'
#NB3: this regex can be used on all elements - but it will match _either_ a 'br'
# _or_ a combination of anything else - because 'br's are Tags, not in a NavigableString

def matchstring(e, rx):
  # Difficulty here: str(ee) may give UnicodeEncodeError with some characters
  # and so may ee.__str__() and repr(ee) (the latter with some \x?? chars).
  # The only thing sure to not give errors is ee.__repr__()
  # However you don't want to use THAT for matching! So use it as a safety net
  # to make sure str() is not called when unicode chars are in there
  s = e.__repr__()
  if s.find('\\u') != -1 or s.find('\\x') != -1:
    return False
  return rx.search(str(e))

# Remove all tags that only contain whitespace
# (do not remove the contents. Move the contents outside; remove the tags.)
def removetagcontainingwhitespace(tagname):
  r = soup.findAll(tagname)
  for e in r:
    ok = 1
    for ee in e.contents:
      if not(matchstring(ee, rx)):
        ok = 0
        break
    if ok:
      movecontentsbefore(e, e)
      e.extract()
      
rxnl = re.compile('\S\n$')
def extractwhitespacefromend(t):
  r = t.contents
  while len(r):
    e = r[-1]
    if e.__class__.__name__ == 'Tag':
      if e.__unicode__() == '<br />':
        e.extract()
      else:
        extractwhitespacefromend(e)
        break
    elif matchstring(e, rx):
      # delete whole NavigableString consisting of whitespace
      e.extract()
    elif matchstring(e, rxe) and not rxnl.search(str(e)):
      # extract whitespace from end of NavigableString (except if it's just a newline for markup; we don't want to get everything on one line...)
      s = rxe.sub('', str(e))
      e.replaceWith(s)
    else:
      break

# Check alignments of all elements inside a certain parent element.
# If alignment of an element is explicitly specified AND equal to the specified parent
#  alignment, then delete that explicit attribute
# If alignment of ALL elements is the same AND NOT equal to the specified parent
# alignment, then change the parent's alignment property IF that is allowed.
#
# NOTES:
# This function currently checks only for the 'align' attribute, which is deprecated.
# There's the 'style="text-align: ..."' which should be used instead
# (should be replaced, but theoretically also checked)
def checkalign(pe, parentalign, pallowchange = ''):

  ## first: special handling for 'implicitly aligning tags', i.e. <center>
  if parentalign == 'center':
    # get rid of all 'center' tags, because they do nothing.
    # (you're generally better off placing its child contents at the same level now,
    # so you can inspect them in one go)
    r = pe.findAll('center', recursive=False)
    for t in r:
      movecontentsbefore(t, t)
      t.extract()

  al = {}
  # non-whitespace NavigableStrings always have alignment equal to the parent element
  # (whitespace strings don't matter; alignment can be changed without visible difference)
  r = pe.findAll(text=lambda x, r=rx: r.match(x)==None, recursive=False)
  if len(r):
    al['inherit'] = True
    # setting 'inherit' effectively means: prevent parent's alignment from being changed

  ## find/index alignment of all tags within pe, and process
  r = pe.findAll(recursive=False)
  for t in r:

    s = t.__repr__() 
    talign = t.get('align')
    if talign:
#NOTE: 'align' can also be "middle"... ignore that for now until I see it being used on non-nivigation-images
      thisalign = talign
      allowchange = 'any'
    elif s.startswith('<center>'):
      thisalign = 'center'
      allowchange = parentalign
    else:
      thisalign = parentalign
      if s.startswith('<p>') or s.startswith('<p '):
        allowchange = 'any'
      else:
        allowchange = ''

    # recurse through subelements first
    tal = checkalign(t, thisalign, allowchange)
    # handling of 'implicitly aligning tags', i.e. <center>:
    if s.startswith('<center>'):
      if 'CHANGE' in tal:
        # align needs change -- which can (only) be done by deleting the tag.
        movecontentsbefore(t, t)
        t.extract()

    else:
      # 'normal' element
      if 'CHANGE' in tal:
        # align needs change
        # (we may end up deleting it just afterwards, but this way keeps code clean)
        #setattr(t, 'align', tal['CHANGE'])
        t['align'] = tal['CHANGE'] ## Does this now always work? Otherwise use __setitem__()?
        talign = tal['CHANGE']

      if talign:
        ## explicit/changed alignment
        if talign == parentalign:
          # delete (now-)superfluous explicit 'align' attribute in tag
          #delattr(t, 'align')
          del t['align']
          al['inherit'] = True
        else:
          # We're just collecting alignments 'not equal to inherited' here;
          # Check after the loop what we want to do about it.
          lastalign = talign
          al[lastalign] = True
      else:
        ## inherited, unchanged alignment
        al['inherit'] = True

  ## After finding/indexing(/changing?) all 'align' from (recursive?) child tags:
  #
  # We can change this collection of elements' (and thus the parent's) alignment
  # IF the parent's "align" property has no influence on any of its kids - i.e.
  # no "inherit" was recorded.
  if len(al) == 1 and ('inherit' not in al) and (pallowchange == 'any' or pallowchange == lastalign):
    # All alignments are the same == lastalign.
    # Indicate to caller that it should change parent's align attribute
    al['CHANGE'] = lastalign
    # Delete any explicit attribute because we will change the parent's.
    for t in pe.findAll(align=lastalign, recursive=False):
      del t['align']

  return al
# Ideas for this routine:
# - if all your stuff is 'center', and more than one (and not inherit), then insert a 'center', place everything inside, and then delete all the explicit align=center from these tags
# - replace 'middle' by 'center'? (align=middle is used for pictures, I've seen sometimes.)

# Filter out attributes from a tag; change some others
#
def mangleattributes(t):
  #t.attrs is list of tuples
  # so if you loop through it, you get tuples back
  # still you can USE it as a dict type. So you can assign and delete stuff by key
  # however you may not delete stuff by key while iterating of the list of attrs! That makes the iterator break off...

  # create list of keys first
  attrs = []
  for attr in t.attrs:
    attrs.append(attr[0])

  for can in attrs:
    cav = t.get(can)
    an = can.lower()
    av = cav.lower()

    if an == 'align':
      # Replace this outdated attribute by a 'class="align-..."' attribute
      #  Assumes you have those classes defined in CSS somewhere!
      # (We can also go for a 'style: align=...' attribute, but I'd like to have less explicit style attributes in the HTML source if I can, so make a 'layer')
      sv = t.get('class')
      if sv:
        # assume this class is not yet present
        t['class'] = sv + ' align-' + av

      else:
        t['class'] = 'align-' + av
      av = ''

    elif an == 'class':
      classes = cav.split()
      for av in classes:
        if av.lower() == 'msonormal':
          classes.remove(av)
      av = ' '.join(classes)

    elif an == 'lang':
      # always remove 'lang' attributes
      av = ''

    elif an == 'style':
      styledefs = av.split(';')
      av = ''
      for s in styledefs:
        (sn, sv) = s.split(':', 1)
        sn = sn.strip()
        sv = sv.strip()

        if sn == 'line-height':
          if sv == '15.1pt' or sv == '100%' or sv == 'normal':
            sv = ''

        elif sn == 'color':
          if sv == 'black' or sv == '#000' or sv == '#000000':
            sv = ''

        elif sn.startswith('margin'):
          if sv.isnumeric() and float(sv) < 0.02:
            sv = ''
      
        elif sn.startswith('mso-'):
          # weird office specific styles? Never check, just delete and hope they didn't do anything
          sv = ''

        if sv:
          if av != '':
            av += '; '
          # gather possibly-chsnged styles
          av += sn + ': ' + sv

    # check if tags have changed
    # also change uppercase attribute names to lower
    if an != can or av != cav.lower():
      if an != can or not av:
        del t[can]
      if av:
        t[an] = av

# Get style attribute from tag, return it as dictionary
def getstyle(t):
  s = t.get('style')
  r = {}
  if s:
    for styledef in s.split(';'):
      (sn, sv) = s.split(':', 1)
      r[sn.strip().lower()] = sv.strip()
  return r

##### Start the action

fname = args[0]
html = open(fname).read()
html = html.replace('\r\n','\n')

########
# Strip superfluous font tag, because FrontPage does stuff
#  like <font> <center> </font> </center>, which makes HTMLTidy wronlgy 
#  'correct' stuff that would be fine if those font tags weren't there.
# Also, accommodate for recursive font tags... because _in between_
#  these idiotic tags there may be legit ones.

tagToStrip = '<font face="' + c_common_font + '">'
tagLenEnd = len('</font>')
pos = 0
found = []
while True:
  # Find a font start/end tag pair, without any other font tags in between
  # Do this by searching for an end tag, and then storing all the start tags
  # leading up to it.
  pe = html.find('</font>', pos)
  if pe == -1:
    break
  #print 'end: ' + str(pe)
  # Find zero or more start tags and store them all
  ps = html.find('<font', pos)
  while (ps < pe and ps != -1):
    #print 'start: ' + str(ps)
    found.append(ps)
    pos = ps + 1
    ps = html.find('<font', pos)

  if len(found) == 0:
    exit('font end tag without start tag found at pos ' + str(pe))
    # The position will likely be wrong since there's already been replacements...

  pos = pe + 1

  # Get last non-processed start tag (this way recursive font tags also work)
  ps = found.pop()
  # Delete corresponding start/end tags from the string, IF it's equal to tagToStrip
  # Otherwise skip (and go on finding/processing next start/end tag)
  if html[ps : ps+len(tagToStrip)] == tagToStrip:
    html = html[:ps] + html[ps+len(tagToStrip):pe] + html[pe+tagLenEnd:]
    pos = pos - len(tagToStrip) - tagLenEnd
  #  print str(ps) + ' ' + str(pe)
  #else: 
  #  print 'skipped: ' + str(ps) + ' ' + str(pe)

##############
#
# Now do some tidying work, using BeautifulSoup

soup = BeautifulSoup(html)

# Delete all script tags
# (I don't know this syntax; just deduced it from the docs :) )
r = soup.findAll('script')
[e.extract() for e in r]

# delete comments
r = soup.findAll(text=lambda text:isinstance(text, Comment))
[e.extract() for e in r]

#Replace b->strong and i->em, for XHTML compliance
# and so that we're sure we are not skipping tags in the code below
r = soup.findAll('b')
for t in r:
  e = Tag(soup, 'strong')
  t.parent.insert(t.indexInParent(), e)
  movecontentsinside(t, e)
  t.extract()
r = soup.findAll('i')
for t in r:
  e = Tag(soup, 'em')
  t.parent.insert(t.indexInParent(), e)
  movecontentsinside(t, e)
  t.extract()

# Remove stupid MSFT 'o:p' tags. Apparently it is best for the document flow,
# if we get rid of some markup whitespace (not &nbsp) inside these tags too...
rx1 = re.compile('^\s+')
rx2 = re.compile('\s+$')
r = soup.findAll('o:p')
for t in r:
  r2 = t.contents
  # check for whitespace at start
  if len(r2) and matchstring(r2[0], rx1):
    s = rx1.sub('', r2[0])
    if s == '':
      r2[0].extract()
    else:
      r2[0].replaceWith(s)
  # check for whitespace at end
  # (r2 may no be empty, after the extract)
  if len(r2) and matchstring(r2[-1], rx2):
    s = rx2.sub('', r2[-1])
    if s == '':
      r2[-1].extract()
    else:
      r2[-1].replaceWith(s)
  if len(r2):
    movecontentsbefore(t, t)
  t.extract()

# Remove tags that only contain whitespace
# (do not remove the contents. Move the contents outside; remove the tags.)
removetagcontainingwhitespace('strong')
removetagcontainingwhitespace('em')
removetagcontainingwhitespace('font')

#NO. Don't do this. Keep the 'b's outside the 'a's... Keep this code for reference, maybe later...
#
# links are rendered in bold, by default.
# Some links have a 'b' around it, which makes no visual difference but
# is an inconsistency in the document structure. Remove it.
#r = soup.findAll('a')
#for e in r:
#  s = e.parent.__repr__()
#  if s[0:3] == '<b>' and s[-4:] == '</b>':
    # the 'b' may have more content than just the link. As long as that's all
    # whitespace, there is still no difference in taking it away.
#    ok = 1
#    for ee in e.parent.contents:
#      if ee != e and not(matchstring(ee, rx)):
#        ok = 0
#        break
#    if ok:
#      ee = e.parent
#      movecontentsbefore(ee, ee)
#      ee.extract()

# Some 'a' tags have 'b' tags surrounding them, and some have 'b' tags inside them.
# Normalize this; 
r = soup.findAll('a')
for t in r:
  r1 = t.findAll('strong', recursive=False)
  if r1:
    r2 = t.findAll(recursive=False)
    if len(r1) == len(r2) and len(t.findAll(text=lambda x, r=rx: r.match(x)==None, recursive=False)) == 0:
      # all tags are 'b' and all navigablestrings are whitespace.
      # Delete the 'b' (can be a chain of multiple, in extreme weird cases)
      for e in r1:
        movecontentsbefore(e, e)
        e.extract()
      # make 'strong' tag and move e inside it
      e = Tag(soup, 'strong')
      t.parent.insert(t.indexInParent(), e)
      e.insert(0, t)

# remove whitespace at end of paragraphs
r= soup.findAll('p')
for t in r:
  extractwhitespacefromend(t)

# remove whitespace just before <br>
# Strictly we only need to move 'HTML whitespace' (&nbsp;), but
# that may be followed by a separate NavigableString holding only '\n'
rxb = re.compile('(?:\&nbsp\;|\s)+$')
r= soup.findAll('br')
for t in r:
  e = t.previousSibling
  while e != None and matchstring(e, rxb):
    # already store 'previous previous', so we can safely extract it
    # (also works around us not knowing whether extract() will actually get rid of a '\n')
    ee = e.previousSibling
    s = rxb.sub('', e)
    if s == '':
      e.extract()
    else:
      e.replaceWith(s)
    e = ee

# Delete tables with one TR having one TD - these are useless
# (take their contents out of the tables)
r = soup.findAll('table')
for t in r:
  r_tr = t.findAll('tr', recursive=False)
  if len(r_tr) == 0:
    t.extract()
  elif len(r_tr) == 1:
    r_td = r_tr[0].findAll('td',recursive=False)
    if len(r_td) == 0:
      t.extract()
    elif len(r_td) == 1:
      #movecontentsbefore(r_td[0], t)
      # content inside a 'td' is left aligned by default, so we can't yank everything
      # out of there just like that.
      e = Tag(soup, 'div')
      e['align'] = 'left'
      t.parent.insert(t.indexInParent(), e)
      movecontentsinside(r_td[0], e)
      t.extract()

# Our HTML uses tables as a way to make bullet points:
# one table with each row having 2 fields, the first of which only
# contains a 'bullet point image'.
# Replace those tables by <ul><li> structures.
rxb = re.compile(c_img_bullet_re)
r = soup.findAll('table')
for t in r:
  r_tr = t.findAll('tr', recursive=False)
  all_bullets = 1
  for tr in r_tr:
    if all_bullets:
      all_bullets = 0
      r_td = tr.findAll('td', recursive=False)
      if len(r_td) == 2:
        # Inspect the first 'td':
        # needs to contain only one 'img' tag.
        # (I don't know how to determine the tag of an element, so do duplicate findAll())
        #r_cont = r_td[0].findAll()
        #if len(r_cont) == 1 and len(r_td[0].findAll('img')) == 1:
        r_cont = filter(lambda x: x != '\n', r_td[0].contents)
        if len(r_cont) == 1:
          s = r_cont[0].__repr__()
          if s[0:5] == '<img ' and s[-2:] == '/>':
            # When is this a bullet point? Look at 'src' tag. That'll do.
            # Is a relative path, so look only at the end.
            s = r_cont[0]['src']
            if rxb.search(s):
              all_bullets = 1
  # After looping through everything, we know if this table contains 'only bullet points'
  if all_bullets:
    # insert ul just before the table
    # (If some of the siblings are NavigableStrings, not inside an element...
    # this actually misplaces stuff and the ul may be inserted _before_ a string
    # when it should be inserted after. I don't know a solution for this atm.)
    e = Tag(soup, 'ul')
    l = t.indexInParent()
    t.parent.insert(l, e)
    # insert li's and move all the contents from the second td's into there
    # (Is it always legal to just 'dump everything' inside a li? Let's hope so.)
    i = 0
    for tr in r_tr:
      ee = Tag(soup,'li')
      e.insert(i, ee)
      r_td = tr.findAll('td', recursive=False)
      #r_cont = r_td[1].findAll()
      # In the preceding code we used findAll() because we assumed that there are no
      # loose NavigableStrings in between tr's or td's.
      # However with the contents of the second td, we can't take that chance.
      r_cont = filter(lambda x: x != '\n', r_td[1].contents)
      if len(r_cont) == 1:
        s = r_cont[0].__repr__()
        # Remark: yes, we should allow for other whitespace (e.g. newline) behind the p...
        # But not right now. We're only doing this nasty frontpage html and it'll do.
        if (s[0:3] == '<p ' or s[0:3] == '<p>') and s[-4:] == '</p>':
          # inside the 'td' there's exactly one paragraph.
          # insert the contents of the paragraph, instead of the paragraph itself.
          movecontentsinside(r_cont[0], ee)
        else:
          # any other case: just insert all contents of the 'td'
          movecontentsinside(r_td[1], ee)
      else:
        movecontentsinside(r_td[1], ee)
      extractwhitespacefromend(ee)
      ee = NavigableString('\n')
      e.insert(i + 1, ee)
      i = i + 2
    t.extract()


# Delete/change superfluous 'align' attributes (and <center> tags sometimes)
checkalign(soup.body, 'left')


# replace 'font color=' with 'span color=' -- it's more XHTML compliant and no hassle
# replace 'font' tags with style attributes. First look if there is a single
# encompassing div/span/p, then look whether font encompasses a single one, otherwise create a 'span' tag in place.
r = soup.findAll('font')
for t in r:
  e = None
  innerdest = False

  ee = t.parent
  s = t.__repr__() 
  if s.startswith('<p>') or s.startswith('<p ' )or s.startswith('<span>') or s.startswith('<span ') or s.startswith('<div>') or s.startswith('<div '):
    r1 = ee.findAll(recursive=False)
    if len(r1) == 1: # only font
      r1 = ee.findAll(text=lambda x, r=rx: r.match(x)==None, recursive=False)
      if len(r1) == 0:
        # parent has only one child tag (the font) and no non-whitespace navstrings
        # so we can dump all our style attributes here
        e = ee
        innerdest = True
  if e is None:
    r1 = ee.findAll(text=lambda x, r=rx: r.match(x)==None, recursive=False)
    if len(r1) == 0:
      r1 = ee.findAll(recursive=False)
      if len(r1) == 1:
        # only one child tag and no non-ws tag
        s = r1[0].__repr__()
        if s.startswith('<p>') or s.startswith('<p ' )or s.startswith('<span>') or s.startswith('<span ') or s.startswith('<div>') or s.startswith('<div '):
          e = r1[0]
  if e is None:
    # cannot use a direct parent/child. Make a new span
    e = Tag(soup, 'span')
    t.parent.insert(t.indexInParent(), e)

  # get the styles which we're going to add to -- as a dict
  estyle = getstyle(e)
  #t.attrs is list of tuples
  # so if you loop through it, you get tuples back
  # still you can USE it as a dict type. So you can assign and delete stuff by key
  # however you may not delete stuff by key while iterating of the list of attrs! That makes the iterator break off...

  # create list of keys first
  attrs = []
  for attr in t.attrs:
    attrs.append(attr[0])
  # iterate over attributes (note: you get them as a list of tuples)
  for can in attrs:
    an = can.lower()
    av = t.get(can)
    sn = ''

    if an == 'color':
      sn = 'color'
    elif an == 'face':
      sn = 'font-family'
    elif an == 'size':
      sn = 'font-size'

    if sn:
      # ignore the property if you want to assign to a span/div/p inside the font tag, and that already has the same property
      if not (innerdest and sn in s):
        estyle[sn] = av
      del t[an]

  # put the style into e
  s = ''
  for sn in estyle:
    if s != '':
      s += '; '
    s += sn + ': ' + estyle[sn]
  e['style'] = s

  # Since the font tag has only above 3 possible attributes, it should be empty now
  # but still check... Do not delete the font tag if it has 'unknown' properties
  if len(t.attrs) == 0:
      movecontentsinside(t, e)
      t.extract()

# Look through tags, changes some attributes
# AND div/span tags without attributes. (There may be those, left by checkalign())
# (This should be under the font-elimination code since that may have put font sizes & colors in a tag, which we will delete here)
for v in ('span', 'div', 'p'):
  for t in soup.findAll(v):
    mangleattributes(t)
    if len(t.attrs) == 0 and (v == 'span' or v == 'div'):
      movecontentsbefore(t, t)
      t.extract()


# The 'real contents' are now at the same level as the 'row of menu buttons' on top and
# bottom, which we don't want. Hence it is not so easy to make an XSLT transform for 
# picking the 'real' body content.
#
# Do: Take the first & last tag out - IF these are paragraphs contain navigation buttons
# (ignore the possibility of NavigableStrings before first/after last tags)
#r = soup.body.findAll(recursive=False)
r = soup.body.contents
rx1 = re.compile('^\<p(?:\s|\>)')
rx2 = re.compile('^\<a href=\"(?:[^\"]*\/)?index.htm\"')
rx3 = re.compile('^\<img src=\"_derived\/[^\>]+\/\>$')
if str(r[0]) == '\n':
  # we want the first newline to remain there,
  # so the body tag will be on a line by itself
  i = 1
else:
  i = 0
v = 3
while v:
  # find whitespace _before_ the real content
  # this will likely be 'markup whitespace' (newlines) that are unnecessary now
  # Removing 'HTML whitespace' (like breaks/nbsp) has its effect on the actual page -but delete it anyway. I think we want to unify 'space at the start' anyway.
  if matchstring(r[i], rx):
    r[i].extract()  ### This actually changes r
  elif matchstring(r[i], rx1):
    if len(r[i].contents) == 0:
      # extract empty paragraph at start -- that's just as "whitespace" as the above
      r[i].extract()
    elif v == 3:
      # look for the buttons
      e = r[i].findNext()
      if matchstring(e, rx2):
        r[i].extract()
        v = 2
      else:
        v = 0 # other nonempty paragraph
    elif v == 2:
      # look for a header title image (which is superfluous because the title's also in the page)
      rr = r[i].findAll()
      if len(rr) == 1 and matchstring(rr[0], rx3):
        r[i].extract()
        v = 1
      else:
        v = 0 # other nonempty paragraph
    else:
      v = 0 # other nonempty paragraph while v==1
  else:
    v = 0 # other tag/NavigableString

# Last
# NB: this is partly effectively extractwhitespacefromend() - but intermixed with empty <p> tags too
v = 2
if str(r[-1]) == '\n':
  # we want the last newline to remain there,
  # so the body tag will be on a line by itself
  i = -2
else:
  i = -1
while v:
  if matchstring(r[i], rx):
    r[i].extract()
    #i = i - 1
  elif matchstring(r[i], rx1):
    if len(r[i].contents) == 0:
      r[i].extract()
      #i = i - 1
    elif v == 2:
      e = r[i].findNext()
      if matchstring(e, rx2):
        r[i].extract()
        #soup.body.findAll(recursive=False)[-1].extract()
        #i = i - 1
        v = 1
      else:
        v = 0 # other nonempty paragraph; quit
    else:
      v = 0 # other nonempty paragraph while v==1
  else:
    v = 0 # other tag/NavigableString



###TODO: remove unnecessary html entities like &ldquo, or stuff?
# no, FG might object to "different" quotes?

print soup
