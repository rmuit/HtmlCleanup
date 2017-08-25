#!/usr/bin/python

# Read old MS FrontPage HTML document and tidy it up.
# Contains site specific functions, so the script will need to be changed somewhat
# for every site.
# Version: 20100908/ploog+ipce.info

from optparse import OptionParser
import os
import re
from BeautifulSoup import BeautifulSoup, Tag, NavigableString, Comment

# We have no options as yet, but still this is a convenient way of printing usage
#usage = "usage: %prog [options] arg1 arg2"
a = OptionParser(usage = "usage: %prog htmlfile",
                 description = "filename should be a HTML file")
(options, args) = a.parse_args()
if len(args) != 1:
  print "Number of command line arguments must be 1!"
  a.print_help()
  exit()

fname = args[0]

### 'constants' for constructs we need to use in site specific code:
#
#  - the font name (used in all illegal font tags which should be stripped out
#    before even feeding the HTML to BeautifulSoup
#  - name of the image which should be converted to 'li' tag when found
#
## if you use this script for different sites, insert favourite way of
## distinguishing between them, here:
if os.path.abspath(fname).find('ipce') != -1:
  c_common_font = 'Book Antiqua, Times New Roman, Times'
  # We now have several themes; as long as we can encode all bullet GIFs into
  # one regexp, we'll keep the current code.
  c_img_bullet_re = '(rom|exp)bul.?.?\.gif$'
else:
  c_common_font = 'Arial, Helvetica'
  c_img_bullet_re = 'posbul.?.?\.gif$'

### THESE REGEXES ARE REFERENCED AS A 'GLOBAL' INSIDE FUNCTIONS
#
# Regexes containing HTML tags. These can be used on all elements but they will
# match _either_ a 'br' _or_ a combination of anything else - because <br>s are
# Tags and are never found inside a NavigableString.
rxglobal_spacehmtl_only = re.compile('^(?:\s|\&nbsp\;|\<br ?\/?\>)+$')
rxglobal_spacehmtl_at_end = re.compile('(?:\s|\&nbsp\;|\<br ?\/?\>)+$')
#
# Regexes usable on NavigableStrings.
# We want to use thse for replacement (specifically by ''). Space excluding
# "&nbsp;" at the start/end of the contents of a tag don't usually influence
# formatting of the output _except_ if they are compound breaking/non-breaking
# spaces. But even if they influence only formatting of the source HTML, we
# explicitly want to 'fix' that for spaces at start/end of tag contents.
#
# Document: does \s include newlines (very probably no), and is that wanted? It
# seems like for 'spaces_only', we want to include newlines too (because this is
# typically used for matching/removing full contents of a tag) but we may not
# want to include them at start/end (because if they are in the document, that's
# probably on purpose because it provides nice formatting that we can preserve)?
rxglobal_spaces_only = re.compile('^\s+$')
rxglobal_spaces_at_start = re.compile('^\s+')
rxglobal_spaces_at_end = re.compile('\s+$')
rxglobal_nbspace_at_end = re.compile('(?:\s|\&nbsp\;)+$')
rxglobal_newline = re.compile('\s*\n+\s*')
# This one is only usable for matching, not replacement:
rxglobal_newline_at_end = re.compile('\S\n$')


###
### Functions 1/3: helper functions which are pretty much general
###

# Return the index of an element inside parent contents.
def indexInParent(slf):
  # (Maybe there is a better way than this; I used to have this in a patched
  # version of the BeautifulSoup.py library 3.1.0.1 itself, before I started
  # working with the non-buggy v3.0.8.1. So I just took the function out
  # and didn't look further.)
  index = 0
  while index < len(slf.parent.contents):
    if slf.parent.contents[index] is slf:
      return index
    index = index + 1
  # If this happens, something is really wrong with the data structure:
  return None

# Move all contents out of one tag, to just before another tag.
def movecontentsbefore(fromwithin, tobefore):
  movecontentsinside(fromwithin, tobefore.parent, indexInParent(tobefore))

# Move all or some (last part of) contents out of one tag, to inside another tag
# (at a specified index; default at the start).
def movecontentsinside(fromwithin, toinside, insertindex = 0, fromindex = 0):
  r = fromwithin.contents
  i = insertindex
  while len(r) > fromindex:
    toinside.insert(i, r[fromindex])
    i = i + 1

# Check if element matches regex; 'safe' replacement for rx.search(str(e))
# where no error will be thrown when e is a tag (as opposed to NavigableString)
# either.
def saferegexsearch(e, rx):
  # Difficulty here: str(ee) may give UnicodeEncodeError with some characters
  # and so may ee.__str__() and repr(ee) (the latter with some \x?? chars).
  # The only thing sure to not give errors is ee.__repr__()
  # However you don't want to use THAT for matching! So use it as a safety net
  # to make sure str() is not called when unicode chars are in there
  #
  # Yeah, I know, it's probably just my limited Python knowledge, that made me
  # write this function...
  # (If it isn't a bug in BeautifulSoup 3.1; probably not.)
  s = e.__repr__()
  if s.find('\\u') != -1 or s.find('\\x') != -1:
    return False
  return rx.search(str(e))

# Remove all tags that only contain whitespace.
# (Do not remove the contents. Move the contents outside; remove the tags.)
def removetagcontainingwhitespace(tagname):
  for e in soup.findAll(tagname):
    ok = 1
    for ee in e.contents:
      if not(saferegexsearch(ee, rxglobal_spacehmtl_only)):
        ok = 0
        break
    if ok:
      movecontentsbefore(e, e)
      e.extract()

# Remove whitespace from start / end of a tag's contents.
def removewhitespace(t):
    # First do end; this includes removing full-whitespace string and also <br>s.
    # (We already have that function and don't want to look at whether it makes
    # sense to refactor it, right now.)
    removewhitespacefromend(t)
    # Then do start. Keep \n at the start if it's there though; that's
    # formatting we want to keep.
    r = t.contents
    if len(r):
        if str(r[0]) == '\n':
          i = 1
        else:
          i = 0
        # We know we have no full-whitespace (because that would have been
        # removed) so we know we will strip only part of the element. If this
        # element is a tag then we don't want to strip anything inside it
        # (because that is not necessarily 'only markup').
        e = r[i]
        if saferegexsearch(e, rxglobal_spaces_at_start):
          s = rxglobal_spaces_at_start.sub('', r[i])
          r[i].replaceWith(s)

# Remove whitespace from the end of a tag's contents.
#
# The definition of the regex we use makes this include non-breaking space. The
# code below apparently makes this include 'HTML' newlines (i.e. <br>s) as well
# as 'markup') newlines... which is slightly odd?
def removewhitespacefromend(t):
  r = t.contents
  while len(r):
    e = r[-1]
    if e.__class__.__name__ == 'Tag':
      if e.__unicode__() == '<br />':
        e.extract()
      else:
        removewhitespacefromend(e)
        break
    elif saferegexsearch(e, rxglobal_spacehmtl_only):
      # Delete whole NavigableString consisting of whitespace.
      e.extract()
    elif saferegexsearch(e, rxglobal_spacehmtl_at_end) and not saferegexsearch(e, rxglobal_newline_at_end):
      # Extract whitespace from end of NavigableString (except when it's just a
      # newline for markup; we don't want to get everything on one line...)
      s = rxglobal_spacehmtl_at_end.sub('', str(e))
      e.replaceWith(s)
    else:
      break

# Remove newlines + superfluous markup spacing from tags.
#
# This should be called for tags that we don't expect to containg any formatting
# of the HTML document which we want to preserve; all content will be collapsed.
def removenewlinesfromcontent(t):
  for e in t.contents:
    if e.__class__.__name__ == 'Tag':
      removenewlinesfromcontent(e)
    elif saferegexsearch(e, rxglobal_newline):
      s = rxglobal_newline.sub(' ', str(e))
      e.replaceWith(s)

# Get style attribute from tag, return it as dictionary
def getstyle(t):
  s = t.get('style')
  r = {}
  if s:
    for styledef in s.split(';'):
      (sa, sv) = s.split(':', 1)
      r[sa.strip().lower()] = sv.strip()
  return r

# Set style (attribute=value).
# attr must be lowercase;
# value must be string type. If value == '', the attribute is deleted.
def setstyle(t, attr, value):
  s = t.get('style')
  r = {}

  ## deconstruct s

  if s:
    for styledef in s.split(';'):
      (sa, sv) = s.split(':', 1)
      r[sa.strip().lower()] = sv.strip()

    ## (re)build s from here

    if attr in r:
      # overwrite the new style and compose the full style string again
      if value != '':
        r[attr] = value
      else:
        del r[attr]
      s = ''
      for sa in r:
        if s != '':
          s += '; '
        s += sa + ': ' + r[sa]
    elif value != '':
      s = s.strip()
      if s != '':
        if not s.endswith(';'):
          s += ';'
        s += ' '
      s += attr + ': ' + value
  else:
    s = attr + ': ' + value

  ## (re)set style

  if s != '':
    t['style'] = s
  #elif 'style' in t.attrs: <-- wrong. attrs returns tuples, not keys
  else:
    # There's no style left (there was only attr, which you just deleted)
    del t['style']


###
### Functions 2/3: helper functions which have logic (like tag/attribute names)
### encoded in them
###

# Get alignment from a tag
# look in attributes 'align' & 'style: text-align' (in that order)
# Return 'left', 'center', 'right' or ''
def getalign(t):
  talign = t.get('align')
  if not talign:
    s = getstyle(t)
    if 'text-align' in s:
      talign = s['text-align']
  #align=middle is seen in some images
  if talign == 'middle':
    talign = 'center'
  return talign

# Set alignment (or delete it, by setting value to '')
# Do this in 'text-align' style attribute
# (we could also e.g. set a certain class; if we wanted)
# and delete the 'align' attrbute.
# Exception: <img>
def setalign(t, value):
  # special handling for images, since the (deprecated?)
  # 'align' tag governs their own alignment - not their contents'
  # alignment. So don't do 'text-align' there.
  s = t.__repr__()
  if not s.startswith('<img '):
    setstyle(t, 'text-align', value)
  elif value != '':
    t['align'] = value
    return

  # text-align is set. Delete the deprecated align attribute (if present)
  del t['align']

#== Note: below was the code I was using somewhere else before,
#   in stead of setstyle(). Maybe we want to go back to using that someday
#   though I don't think so...
      # Replace this outdated attribute by a 'class="align-..."' attribute
      #  Assumes you have those classes defined in CSS somewhere!
      # (We can also go for a 'style: text-align=...' attribute, but I'd like to have less explicit style attributes in the HTML source if I can, so make a 'layer')
      #sv = t.get('class')
      #if sv:
      #  # assume this class is not yet present
      #  t['class'] = sv + ' align-' + av

      #else:
      #  t['class'] = 'align-' + av
      #av = ''
#===

# Check alignments of all elements inside a certain parent element.
# If alignment of an element is explicitly specified AND equal to the specified parent
#  alignment, then delete that explicit attribute
# If alignment of ALL elements is the same AND NOT equal to the specified parent
# alignment, then change the parent's alignment property IF that is allowed.
def checkalign(pe, parentalign, pallowchange = ''):

  ## first: special handling for 'implicitly aligning tags', i.e. <center>
  if parentalign == 'center':
    # get rid of all 'center' tags, because they do nothing.
    # (you're generally better off placing its child contents at the same level now,
    # so you can inspect them in one go)
    for t in pe.findAll('center', recursive=False):
      movecontentsbefore(t, t)
      t.extract()

  al = {}
  # Non-whitespace NavigableStrings always have alignment equal to the parent element.
  # (Whitespace strings don't matter; alignment can be changed without visible difference.)
  r = pe.findAll(text=lambda x, r=rxglobal_spacehmtl_only: r.match(x)==None, recursive=False)
  if len(r):
    # Setting 'inherit' effectively means: prevent parent's alignment from being changed.
    al['inherit'] = True

  ## Find/index alignment of all tags within pe, and process them.
  for t in pe.findAll(recursive=False):

    s = t.__repr__()
    talign = getalign(t)
    if talign:
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

    # Recurse through subelements first.
    tal = checkalign(t, thisalign, allowchange)
    # Handling of 'implicitly aligning tags', i.e. <center>:
    if s.startswith('<center>'):
      if 'CHANGE' in tal:
        # align needs change -- which can (only) be done by deleting the tag.
        movecontentsbefore(t, t)
        t.extract()

    else:
      # 'Normal' element.
      if 'CHANGE' in tal:
        # align needs change. (We may end up deleting it just afterwards, but
        # this way keeps code clean)
        setalign(t, tal['CHANGE'])
        talign = tal['CHANGE']

      if talign:
        ## Explicit/changed alignment.
        if talign == parentalign:
          # Delete (now-)superfluous explicit 'align' attribute in tag.
          setalign(t, '')
          al['inherit'] = True
        else:
          # We're just collecting alignments 'not equal to inherited' here;
          # check after the loop what we want to do about it.
          lastalign = talign
          al[lastalign] = True
      else:
        ## Inherited, unchanged alignment.
        al['inherit'] = True

  ## After finding/indexing(/changing?) all 'align' from (recursive?) child tags:
  #
  # We can change this collection of elements' (and thus the parent's) alignment
  # IF the parent's "align" property has no influence on any of its kids - i.e.
  # no "inherit" was recorded.
  if len(al) == 1 and ('inherit' not in al) and (pallowchange == 'any' or pallowchange == lastalign):
    # All alignments are the same == lastalign.
    # Indicate to caller that it should change parent's align attribute.
    al['CHANGE'] = lastalign
    # Delete any explicit attribute because we will change the parent's.
    for t in pe.findAll(align=lastalign, recursive=False):
      setalign(t, '')

  return al
# Ideas for this routine:
# - if all your stuff is 'center', and more than one (and not inherit), then insert a 'center', place everything inside, and then delete all the explicit align=center from these tags
# - replace 'middle' by 'center'? (align=middle is used for pictures, I've seen sometimes.)


# Filter out attributes from a tag; change some others.
#
# tagname is really a duplicate argument that could be derived from t
# but stupidly, there's no nice argument for that?
def mangleattributes(t, tagname):
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
      # Replace deprecated align attribute by newer way
      # (Unlike the below, this call already resets the 'align' attribute
      #  itself, so we do not set av to '')
      setalign(t, av)

    elif an == 'margin-top':
      # on ploog, this is present in almost every paragraph. Should be made into standard css definition.
      if tagname == 'p':
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
        if s.strip() != '':
          (sn, sv) = s.split(':', 1)
          sn = sn.strip()
          sv = sv.strip()

          if sn == 'line-height':
            if sv == '15.1pt' or sv == '15.1 pt' or sv == '100%' or sv == 'normal':
              sv = ''

          elif sn == 'color':
            if sv == 'black' or sv == '#000' or sv == '#000000':
              sv = ''

          elif sn == 'text-autospace':
            if sv == 'none':
              sv = ''

          elif sn == 'font-family':
            if sv == 'arial' and c_common_font.find('Arial') == 0:
              sv = ''

          elif sn == 'font-size':
            #on ploog, I see '12pt' and '3' and I see no difference
            # Possibly, this should only be stripped on ploog. Use trick for that
            if (sv == '12pt' or sv == '3') and c_common_font.find('Arial') == 0:
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

##### Start the action

html = open(fname).read()
html = html.replace('\r\n','\n')

###
### Functions -I mean functionality- 3/3:
###   Helper functionality that operates on the HTML (mangles it) BEFORE it
###   gets parsed by BeautifulSoup.
### NOTES:
### - For now I didn't convert this to a function because it would only imply
###   passing a huge 'html' string as the argument & return value
### - but now, there are a few lines of 'global' code which are executed already
###   (the ones filling the html string)
###

#####
#
# Clean up screwy HTML before parsing - #1:
#
# Strip superfluous font tag, because FrontPage does stuff
#  like <font> <center> </font> </center>, which makes HTMLTidy wronlgy
#  'correct' stuff that would be fine if those font tags weren't there.
# Also, accommodate for recursive font tags... because _in between_
#  these idiotic tags there may be legit ones.
#
# We've seen cases where there are also font tags containing _just_ the first
# family, and we will treat that as equal - i.e. also superfluous / needs to be
# stripped.
font_families = [ c_common_font ]
p = c_common_font.find(',')
if (p > 0):
  font_families.append( c_common_font[:p].strip() )

len_end_tag = len('</font>')
for font_family in font_families:
    s_tag_to_strip = '<font face="' + font_family + '">'
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
      # Delete corresponding start/end tags from the string, IF it's equal to s_tag_to_strip
      # Otherwise skip (and go on finding/processing next start/end tag)
      if html[ps : ps + len(s_tag_to_strip)] == s_tag_to_strip:
        html = html[:ps] + html[ps + len(s_tag_to_strip) : pe] + html[pe + len_end_tag : ]
        pos = pos - len(s_tag_to_strip) - len_end_tag
      #  print str(ps) + ' ' + str(pe)
      #else:
      #  print 'skipped: ' + str(ps) + ' ' + str(pe)

#####
#
# Clean up screwy HTML before parsing - #2:
#
# solve <b><p > .... </b> ... </p> by putting <b> inside <p>
# (if not, BeatifulSoup will put a </p> before the </b> which will mess up formatting)
rx1 = re.compile('\<b\>(\s*\<p.*?\>)(.*?)\<\/b>', re.S)
for r in rx1.finditer(html):
  if r.group(2).find('/p>') == -1:
    html = html[:r.start()] + r.group(1) + '<b>' + html[r.start(2):]
    # since html stays just as long, the finditer will be OK?

##############
###
### Now do the tidying work, using BeautifulSoup

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
for t in soup.findAll('b'):
  e = Tag(soup, 'strong')
  t.parent.insert(indexInParent(t), e)
  movecontentsinside(t, e)
  t.extract()
for t in soup.findAll('i'):
  e = Tag(soup, 'em')
  t.parent.insert(indexInParent(t), e)
  movecontentsinside(t, e)
  t.extract()

# Remove stupid MSFT 'o:p' tags. Apparently it is best for the document flow,
# if we get rid of some markup whitespace (not &nbsp) inside these tags too...
for t in soup.findAll('o:p'):
  removewhitespace(t)
  r2 = t.contents
  if len(r2):
    movecontentsbefore(t, t)
  t.extract()

# Remove non-block tags that only contain whitespace.
# (Do not remove the contents. Move the contents outside; remove the tags.)
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
#      if ee != e and not(saferegexsearch(ee, rxglobal_spacehmtl_only)):
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
    if len(r1) == len(r2) and len(t.findAll(text=lambda x, r=rxglobal_spacehmtl_only: r.match(x)==None, recursive=False)) == 0:
      # all tags are 'b' and all navigablestrings are whitespace.
      # Delete the 'b' (can be a chain of multiple, in extreme weird cases)
      for e in r1:
        movecontentsbefore(e, e)
        e.extract()
      # make 'strong' tag and move e inside it
      e = Tag(soup, 'strong')
      t.parent.insert(indexInParent(t), e)
      e.insert(0, t)

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
      # content inside a 'td' is left aligned by default, so we
      # need to accomodate for that.
      e = Tag(soup, 'div')
      e['style'] = 'text-align: left'
      t.parent.insert(indexInParent(t), e)
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
            # Is a relative path, so it's OK to look only at the end (which is
            # encoded in the regexp).
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
    # Again: content inside a 'td' is left aligned by default, so we
    # need to accomodate for that.
    e['style'] = 'text-align: left'
    l = indexInParent(t)
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
      removewhitespacefromend(ee)
      ee = NavigableString('\n')
      e.insert(i + 1, ee)
      i = i + 2
    t.extract()


# Replace 'font color=' with 'span color=' -- it's more XHTML compliant and no hassle
# Replace 'font' tags with style attributes. First look if there is a single
# encompassing div/span/p, then look whether font encompasses a single one,
# otherwise create a 'span' tag in place.
#
# ^^ "no hassle" IS NOT ACTUALLY TRUE in the last case! In cases where a font
# tag surrounds one or several block-level elements, and putting a span there is
# frowned upon, if not illegal, in that case. However, leaving a 'font' tag
# might be equally bad... For the moment, we are just hoping that we have
# cleaned up all font tags that fit this case, above. (Maybe we should clean up
# some code in the below block instead.)
r = soup.findAll('font')
for t in r:
  e = None
  innerdest = False

  ee = t.parent
  s = t.__repr__()
  if s.startswith('<p>') or s.startswith('<p ') or s.startswith('<span>') or s.startswith('<span ') or s.startswith('<div>') or s.startswith('<div '):
    r1 = ee.findAll(recursive=False)
    if len(r1) == 1: # only font
      r1 = ee.findAll(text=lambda x, r=rxglobal_spacehmtl_only: r.match(x)==None, recursive=False)
      if len(r1) == 0:
        # Parent has only one child tag (the font) and no non-whitespace
        # navstrings so we can dump all our style attributes here.
        e = ee
        innerdest = True
  if e is None:
    r1 = ee.findAll(text=lambda x, r=rxglobal_spacehmtl_only: r.match(x)==None, recursive=False)
    if len(r1) == 0:
      r1 = ee.findAll(recursive=False)
      if len(r1) == 1:
        # Only one child tag and no non-ws tag.
        s = r1[0].__repr__()
        if s.startswith('<p>') or s.startswith('<p ' )or s.startswith('<span>') or s.startswith('<span ') or s.startswith('<div>') or s.startswith('<div '):
          e = r1[0]
  if e is None:
    # Cannot use a direct parent/child. Make a new span.
    # WARNING: see comment on top of this section.
    e = Tag(soup, 'span')
    t.parent.insert(indexInParent(t), e)

  # Get the styles which we're going to add to -- as a dict.
  estyle = getstyle(e)
  # t.attrs is list of tuples, so if you loop through it, you get tuples back.
  # Still, you can USE it as a dict type. So you can assign and delete stuff by
  # key; however, you may not delete stuff by key while iterating of the list of
  # attrs! That makes the iterator break off...

  # Create list of keys first.
  attrs = []
  for attr in t.attrs:
    attrs.append(attr[0])
  # Iterate over attributes. (Note: you get them as a list of tuples).
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
      # ignore the property if you want to assign to a span/div/p inside the
      # font tag, and that already has the same property.
      if not (innerdest and sn in s):
        estyle[sn] = av
      del t[an]

  # Put the style into e
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


# Delete/change superfluous alignment attributes (and <center> tags sometimes)
checkalign(soup.body, 'left')


# Look through tags, change some attributes if necessary, AND remove div/span
# tags without attributes. (There may be <div>s left by checkalign(); often
# there are also unnecessary <span>s inside <p>s.)
# (This should be after the font-elimination code since that may have put font
# sizes & colors in a tag, which we will delete here.)
#
# (h2 / h4 tags with cleanable attributes found in p-loog.info)
for tagname in ('span', 'div', 'p', 'h2', 'h3', 'h4'):
  for t in soup.findAll(tagname):
    # pass v as second argument. I know that's duplicate but t has no easy property to derive v from?
    mangleattributes(t, tagname)
    if len(t.attrs) == 0 and (tagname == 'span' or tagname == 'div'):
      movecontentsbefore(t, t)
      t.extract()

# Remove whitespace just before <br>.
# Strictly we only need to move 'HTML whitespace' (&nbsp;), but that may be
# followed by a separate NavigableString holding only '\n'.
for t in soup.findAll('br'):
  e = t.previousSibling
  while e != None and saferegexsearch(e, rxglobal_nbspace_at_end):
    # already store 'previous previous', so we can safely extract it
    # (also works around us not knowing whether extract() will actually get rid of a '\n')
    ee = e.previousSibling
    s = rxglobal_nbspace_at_end.sub('', e)
    if s == '':
      e.extract()
    else:
      e.replaceWith(s)
    e = ee

# When inside a paragraph, replace (exactly) two consecutive <br>s by a
# paragraph ending + start.
for t in soup.findAll('br'):
  # Thanks to previous, newlines before brs have gone so we can just do nextSibling.
  t2 = t.nextSibling
  if t2.__repr__() == '<br />':
    e = t.previousSibling
    if e.__repr__() != '<br />':
      e = t2.nextSibling
      if e.__repr__() != '<br />':
        pe = t.parent
        s = pe.__repr__()
        if s.startswith('<p>') or s.startswith('<p '):
          # We have exactly two <br>s, inside a <p>.
          # Move contents after t2 to a new paragraph.
          e = t2.nextSibling
          if e == None:
            # The two br's were at the end of a paragraph. Weirdness.
            # Move them outside (just after) the paragraph.
            pe.parent.insert(indexInParent(pe) + 1, t2)
            pe.parent.insert(indexInParent(pe) + 1, t)
          else:
            i = indexInParent(pe) + 1
            e = NavigableString('\n')
            pe.parent.insert(i,e)
            e = Tag(soup, 'p')
            pe.parent.insert(i + 1, e)
            movecontentsinside(pe, e, 0, indexInParent(t2) + 1)
            t2.extract()
            t.extract()
# If the end of the existing / start of the new paragraph) is now markup
# whitespace, that will be removed below.


# The following needs to be done _after_ removing <span>s inside <p>s:

for tagname in ('span', 'p', 'h2', 'h3', 'h4', 'li'):
  for t in soup.findAll(tagname):
    # Remove newlines in the tags which are supposed to have 'simple' contents.
    # (We've seen paragraphs containing contents which are indented and
    # double-spaced, which means someone has been writing it like that in
    # Frontpage but we really don't need that. We've also seen e.g. h2 tags with
    # two newlines in the middle of the title.)
    removenewlinesfromcontent(t)
    # Remove whitespace at start/end of 'position' tags too, to achieve better
    # markup. Don't do 'purely inline' tags (like <span> usually is) because
    # that may affect rendering if there is no space just outside of the tag.
    # (We've seen this is necessary in p and li; we just do the rest too because
    # why not. WARNING: This removes <br> fron the end too which may not always
    # be a great idea, but we won't rewrite that part until we see trouble with
    # it.)
    if tagname != 'em':
      removewhitespace(t)

#####
#####
## Code below here is really custom. It removes certain contents from the top/
## bottom of the HTML. You may have no use for it; please remove.
## Only keep the last 'print' statement.

# The 'real contents' are now at the same level as the 'row of menu buttons' on top and
# bottom, which we don't want. Hence it is not so easy to make an XSLT transform for
# picking the 'real' body content.
#
# Do: Take the first & last tag out - IF these are paragraphs contain navigation buttons
# (ignore the possibility of NavigableStrings before first/after last tags)
rx_p_start = re.compile('^\<p(?:\s|\>)')
# Checks if the array of elements is a list of button links.
def isbuttonlinks(elements):
    buttonlink_found = False
    # (Testing assumption:) all elements on this level must be 'a' tags.
    for e in elements:
        if saferegexsearch(e, rxglobal_spacehmtl_only):
          continue
        s = e.__repr__()
        if not s.startswith('<a '):
          return False
        href = e.get('href')
        if not href:
          return False
        if href.endswith('index.htm') or  href.endswith('nieuw.htm'):
          # This is not always the first buttonn (that may be a 'previous' link
          # with an arbitrary name) but if we encounter this, we assume these
          # are all button links.
          buttonlink_found = True
    return buttonlink_found

# button links. Usually there's one to the index page but not always
# the 'nieuw' is for the p-loog index page which doesn't
#rx_buttonlink = re.compile('^\<a href=\"(?:[^\"]*\/)?(?:index|nieuw).htm\"')
rx_titleimg = re.compile('^\<img .*src=\"_derived\/[^\>]+\/\>$')

# Remove button links from the page top.
# The thing we want to inspect (for removal) will be r[i], where i=0 or 1.
r = soup.body.contents
if str(r[0]) == '\n':
  # We want the first newline to remain there, so the body tag will be on a line
  # by itself.
  i = 1
else:
  i = 0

v = 3
while v >= 0:
  # Find whitespace _before_ the real content. This will likely be 'markup
  # whitespace' (newlines) that is unnecessary now.
  # Removing 'HTML whitespace' (like breaks/nbsp) has its effect on the actual
  # page; delete it anyway. I think we want to unify 'space at the start'.
  if saferegexsearch(r[i], rxglobal_spacehmtl_only):
    r[i].extract()  ### This actually changes r. Then loop.
  elif saferegexsearch(r[i], rx_p_start):
    if len(r[i].contents) == 0:
      # Extract empty paragraph at start ; that's just as "whitespace" as the above.
      r[i].extract()
    elif v:
      if v == 3 or v == 1:
        # Look for the buttons (only once); sometimes these are above,
        # sometimes below the title image.
        if isbuttonlinks(r[i]):
          r[i].extract()
          v -= 1

          # If, right after the paragraph with buttons, there's again a paragraph
          # containing links to categories... delete that too.
          # OR NOT? ... leave that idea for now...
          continue
      if v == 3 or v == 2:
        # look for a header title image (which is superfluous because the title's also in the page)
        rr = r[i].findAll()
        if len(rr) == 1 and saferegexsearch(rr[0], rx_titleimg):
          r[i].extract()
          v -= 2
          continue
      v = -1 # other nonempty paragraph
    else:
      v = -1 # other nonempty paragraph while v==0
  else:
    v = -1 # other tag/NavigableString

# Remove button links from the page bottom. Kind-of the same code but not fully.
# NB: this is partly effectively removewhitespacefromend() - but intermixed with empty <p> tags too
if str(r[-1]) == '\n':
  # we want the last newline to remain there,
  # so the body tag will be on a line by itself
  i = -2
else:
  i = -1

v = 3
while v:
  if saferegexsearch(r[i], rxglobal_spacehmtl_only):
    r[i].extract()
    #i = i - 1
  elif saferegexsearch(r[i], rx_p_start):
    if len(r[i].contents) == 0:
      r[i].extract()
      #i = i - 1
    elif v:
      if v == 3 or v == 1:
        # Look for the buttons (only once); sometimes these are above,
        # sometimes below the title image.
        if isbuttonlinks(r[i]):
          r[i].extract()
          v -= 1
          # see comment above?
          continue
      if v == 3 or v == 2:
          e = r[i].findNext()
          if saferegexsearch(e, rx_titleimg):
            r[i].extract()
            #soup.body.findAll(recursive=False)[-1].extract()
            #i = i - 1
            v = 1
          continue
      v = -1 # other nonempty paragraph; quit
    else:
      v = 0 # other nonempty paragraph while v==1
  else:
    v = 0 # other tag/NavigableString

###TODO: remove unnecessary html entities like &ldquo, or stuff?
# no, FG might object to "different" quotes?

# BeautifulSoup (at least 3.x tested so far) outputs <br />, which is kind-of
# illegal and certainly unnecessary as HTML.
print str(soup).replace('<br />','<br>')
