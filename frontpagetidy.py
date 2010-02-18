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

# Find the current element's index in the parent's "content"(list)
# This is sorely lacking functionality in BeautifulSoup(?)
# and it's really needed because findPreviousSiblings() just does not cut it.
# (That, like findAll, can only return/count Tags OR NavigableStrings)
#
# This function is NOT AT ALL perfect. You can only call it for an element that is
# unique among its siblings -- if there's an equal element somewhere, you may
# get the wrong index.
def indexinparentcontents(e):
  r = e.parent.contents
  i = 0
  while i < len(r):
    if r[i] == e:
      return i
    i = i + 1
  exit('Internal error in indexinparentcontents(): cannot find myself! Dying...')

# move all contents out of one tag, to just before the other tag
def movecontentsbefore(fromwithin, tobefore):
  movecontentsinside(fromwithin, tobefore.parent, indexinparentcontents(tobefore))

def movecontentsinside(fromwithin, toinside, startindex=0):
  #ee = fromwithin.find()
  #i = 0
  #while ee:
  #  toinside.insert(i, ee)
  #  i = i + 1
  #  ee = fromwithin.find()
  r = fromwithin.contents
  i = startindex
  # Rules:
  # - the last element in the contents array gets 'stuck' in its source sometimes -
  # which means that an insert is a no-op (since an element can't be in two places
  # at once). This is not really bad as it always seems to be a newline or breakpoint,
  # but it's irritating in that we need to accomodate the code for this...
  # - when we do an 'insert' of an element (to somewhere else) of an element of r,
  # it automatically disappears from r. So we can keep inserting from the first position.
  while len(r):
    l1 = len(r)
    toinside.insert(i, r[0])
    i = i + 1
    l2 = len(r)
    if l1 == 1 and l2 == 1:
      # maybe we should still insert the thing? I don't know. For now, ignore.
      return

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
  r =  nonwhitenavstrings(pe)
  if len(r):
    al['inherit'] = True
    # setting 'inherit' effectively means: prevent parent's alignment from being changed

  ## find/index alignment of all tags within pe, and process
  r = pe.findAll(recursive=False)
  for t in r:

    s = t.__repr__() 
    talign = getattr(t, 'align')
    if talign:
#NOTE: 'align' can also be "middle"... ignore that for now until I see it being used on non-nivigation-images
      thisalign = talign
      allowchange = 'any'
    elif s == '<center>':
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
    if s == '<center>':
      if 'CHANGE' in tal:
        # align needs change -- which can (only) be done by deleting the tag.
        movecontentsbefore(t, t)
        t.extract()

    else:
      # 'normal' element
      if 'CHANGE' in tal:
        # align needs change
        # (we may end up deleting it just afterwards, but this way keeps code clean)
        setattr(t, 'align', tal['CHANGE'])
        talign = tal['CHANGE']

      if talign:
        ## explicit/changed alignment
        if talign == parentalign:
          # delete (now-)superfluous explicit 'align' attribute in tag
          delattr(t, 'align')
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
      delattr(t, 'align')

  return al
# Ideas for this routine:
# - if all your stuff is 'center', and more than one (and not inherit), then insert a 'center', place everything inside, and then delete all the explicit align=center from these tags
# - replace 'middle' by 'center'? (align=middle is used for pictures, I've seen sometimes.)
# - write: 'style="text-align:' instead of 'align=' (See comment at function start)
#   OR even better: 'class=align-***'

#Helper functions...
# apparently referencing t['align'] does not always work. (Bug in BeautifulSoup?)
# Some attributes (I've seen ones without siblings) give AttributeError deep in BeautifulSoup.py:
# AttributeError("'NoneType' object has no attribute 'next'",)
def getattr(t, an):
  try:
    av = t[an]
  except KeyError:
    av = ''
  except AttributeError:
    av = ''
    for a in t.attrs:
      if a[0] == an:
        av = a[1]
        break
  return av
def delattr(t, an):
  try:
    del t[an]
  except KeyError:
    pass
  except AttributeError:
    for a in t.attrs:
      if a[0] == an:
        t.attrs.remove(a)
        break
def setattr(t, an, av):
  try:
    t[an] = av
  except AttributeError:
    for a in t.attrs:
      if a[0] == an:
        t.attrs.remove(a)
        break
    t.attrs.append((an, av))

def nonwhitenavstrings(e):
  # (Apparently we can use variables from outside the context in below lambda function,
  # i.e. the defined compiled regex for whitespace)
  #pe.findAll(text=lambda x, r=rx: not r.match(x))
  #r = filter((lambda x, rr=rx: rr.match(x)), pe.findall(text=True, recursive=False))
  # Lambda functions don't seem to work - which may be because of the same internal error
  # that forces us to create above setattr() et al functions.
  # And the regexp cannot be negated. So:
  alltext = e.findAll(text=re.compile('^(?:\&nbsp\;|\<br\s*\/\>|\s)+$'), recursive=False)
  whitespace = e.findAll(text=True, recursive=False)
  # difference of lists
  r = [ee for ee in alltext if not ee in whitespace]
  #r = filter((lambda x, r=nr: x not in r), pe.findAll(text=True))
  return r

rx = re.compile('^(?:\&nbsp\;|\<br\s*\/\>|\s)+$')
#NB: the \n and ' ' are probably not necessary here because they do not affect the 
# rendering of the document (and taking the '\n' away as we are doing now may
# be worse for readability of the source?) ... and if we took the '\n' out of here,
# we would not have the problems with 'sticky newlines at end of contents' either...
# ...but I'll leave it in anyway, until I'm sure. Things work now, anyway.
#NB2: above is not really correct. They should be in the regexp
# because strings can be compound, like '\r\n        &nbsp;&nbsp;'

def matchstring(e, rx):
  # Difficulty here: str(ee) may give UnicodeEncodeError with some characters
  # and so may ee.__str__() and repr(ee).
  # The only thing sure to not give errors is ee.__repr__()
  # However you don't want to use THAT for matching! So use it as a safety net
  # to make sure str() is not called when unicode chars are in there
  s = e.__repr__()
  if s.find('\\u') != -1 or s.find('\\x') != -1:
    return False
  return rx.search(str(e))


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
  t.parent.insert(indexinparentcontents(t), e)
  movecontentsinside(t, e)
  t.extract()
r = soup.findAll('i')
for t in r:
  e = Tag(soup, 'em')
  t.parent.insert(indexinparentcontents(t), e)
  movecontentsinside(t, e)
  t.extract()

# Remove all 'b' that only contain whitespace
# (do not remove the contents. Move the contents outside; remove the tags.)
r = soup.findAll('strong')
for e in r:
  ok = 1
  for ee in e.contents:
    if not(matchstring(ee, rx)):
      ok = 0
      break
  if ok:
    movecontentsbefore(e, e)
    e.extract()


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

# Look through 'span' tags.
# Delete 'lang' and 'style' attributes from it; if it's then empty, delete all of it
# (I know this is DANGEROUS, as some style attributes might actually be useful
#  but I haven't seen any yet. So advantages outweigh dangers, so far.)
r = soup.findAll('span')
for t in r:
  delattr(t, 'lang')
  delattr(t, 'style') ###### DANGER?
  if len(t.attrs) == 0:
    movecontentsbefore(t, t)
    t.extract()

# replace 'font color=' with 'span color=' -- it's more XHTML compliant and no hassle
r = soup.findAll('font')
for t in r:
  if len(t.attrs) == 1:
    v = getattr(t, 'color')
    if v:
      if v == 'black' or v == '0' or v == '#000' or v == '#000000':
        # delete black color definition, because the general color is already black.
        # (There is danger in this, because this font declaration could be inside a redefined color area!
        # But I haven't seen that so far, so the advantages are bigger than the danger.)
        movecontentsbefore(t, t)
      else:
        e = Tag(soup, 'span')
        setattr(e, 'color', v)
        t.parent.insert(indexinparentcontents(t), e)
        movecontentsinside(t, e)
      t.extract()

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
for e in r:
  r1 = e.findAll('strong', recursive=False)
  if r1:
    r2 = e.findAll(recursive=False)
    if len(r1) == len(r2) and len(nonwhitenavstrings(e)) == 0:
      # all tags are 'b' and all navigablestrings are whitespace.
      # Delete the 'b' (can be a chain of multiple, in extreme weird cases)
      for t in r1:
        movecontentsbefore(t, t)
        t.extract()
      # make 'strong' tag and move e inside it
      t = Tag(soup, 'strong')
      e.parent.insert(indexinparentcontents(e), t)
      t.insert(0, e)
      
def extractwhitespacefromend(t):
  # accomodate for stupid newline at last of contents not wanting to be extracted
  i = -1
  r = t.contents
  while len(r)+i>=0 and matchstring(r[i], rx):
    l = len(r)
    r[i].extract()
    if len(r) == l:
      # this should hot happen so apparently the newline at the end would not be extracted.
      # ignore it and go further back inside the string.
      i = i - 1
    #else:
    #  # reset. Try again, against hope...
    #  i = -1

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
      t.parent.insert(indexinparentcontents(t), e)
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
    l = indexinparentcontents(t)
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

# There may be empty 'div's now, without attributes.
# (Maybe assigned by the code which stripped tables, and then the align attribute got removed by checkalign())
# Delete them.
for t in soup.findAll('div'):
  if len(t.attrs) == 0:
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
v = 2
while v:
  # find whitespace _before_ the real content
  # this will likely be 'markup whitespace' (newlines) that are unnecessary now
  # Removing 'HTML whitespace' (like breaks/nbsp) has its effect on the actual page -but delete it anyway. I think we want to unify 'space at the start' anyway.
  if matchstring(r[0], rx):
    r[0].extract()  ### This actually changes r
  elif matchstring(r[0], rx1):
    if len(r[0].contents) == 0:
      # extract empty paragraph at start -- that's just as "whitespace" as the above
      r[0].extract()
    elif v == 2:
      # look for the buttons
      e = r[0].findNext()
      if matchstring(e, rx2):
        r[0].extract()
        v = 1
      else:
        v = 0 # other nonempty paragraph
    else:
      v = 0 # other nonempty paragraph while v==1
  else:
    v = 0 # other tag/NavigableString

# Last
# NB: this is partly effectively extractwhitespacefromend() - but intermixed with tags too
v = 2
i = len(r)-1
while v:
  if matchstring(r[i], rx):
    # bug#1: first time, a random (the first) newline is deleted from r, instead of the one we want,
    # 2nd time, nothing is deleted at all
    # but the way we are handling it now (with i=i-1) should accomodate for things...
    if r[i] != '\n':
      # on second thought... because of the bug, newlines are deleted all over the place
      # and that's worse than not deleting them at all (from the end)?
      r[i].extract()
    i = i - 1
  elif matchstring(r[i], rx1):
    if len(r[i].contents) == 0:
      # last paragraph is empty. This happens sometimes.
      # extract and try next one. (r is changed)
      ##r[i].extract()
      ##Working around bug #2: deleting the _last tag_ from a _contents_ array may also go wrong.
      #(actually test show that it still goes wrong; empty paragraphs are extracted from the wrong position. But at least no other random tags are deleted...)
      soup.body.findAll(recursive=False)[-1].extract()
    elif v == 2:
      e = r[i].findNext()
      if matchstring(e, rx2):
        ##r[i].extract()
        soup.body.findAll(recursive=False)[-1].extract()
        v = 1
      else:
        v = 0 # other nonempty paragraph; quit
    else:
      v = 0 # other nonempty paragraph while v==1
  else:
    v = 0 # other tag/NavigableString



###TODO: remove unnecessary html entities like &ldquo, or stuff?
# no, FG might object to "different" quotes?

###TODO: delete EM with only whitespace in them (like b)
###TODO: delete whitespace _at end of_ a navigablestring, in that function
###TODO: delete whitespace _nested_ inside last tags, in that routine (see what effects it has on library.htm)
print soup
