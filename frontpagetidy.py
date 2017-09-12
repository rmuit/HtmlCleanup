#!/usr/bin/python

# Read old MS FrontPage HTML document and tidy it up.
# Contains site specific functions, so the script will need to be changed
# somewhat for every site. Also: read the TODOs in the code for using this on
# non-FrontPage documents.

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

### 'constants' for constructs we need to use in site specific code, or
### functionality that feels best to be able to turn on/off:
#
# - Remove atrributes mentioned in this two-dimensional dict. First key is
#   tagname or '*' to remove the specified attributes for all tags; second key
#   attribute name (no '*' implemented). Values can be a single attribute value
#   or a list of values for which the attribute should be removed. The single
#   value '*' will always remove the attribute.
# There are also attributes which are 'hardcoded' and will always be removed/
# changed; see the code.
c_remove_attributes = {
  # <font> tags will be converted to spans with their attribute names converted
  # to style names. Regardless, to remove the common font-family: specify
  # 'face' here. It often happens that two font definitions are used: one with
  # several families and one with only the first. To remove both, specify both.
  'font': {'face': ['Book Antiqua, Times New Roman, Times', 'Book Antiqua']},
  # Remove any language value from any tag.
  '*': {
    'lang': '*',
  },
  # We've seen a website where 'margin-top' is present in almost any
  # paragraph and we don't want this in the output.
  # 'p': { 'margin-top': '*' }
}
# - Same for the 'style' attribute. (Mentioning 'style' in c_remove_attributes
#   is possible but discouraged; define styles to remove here, in the same way.)
c_remove_styles = {
  '*': {
    'line-height': ['100%', 'normal', '15.1 pt'],
    # Remove black from everywhere. (May not be what we always want...)
    'color': ['black', '#000', '#000000'],
    'text-autospace': 'none',
  },
  'h2': {'color' : '#996600'},
  'h3': {'color' : '#999900'},
}
# - Images which should be converted to 'li' tag when found inside a table with
#   a specific structure. Format: regex.
c_img_bullet_re = '(rom|exp)bul.?.?\.gif$'
# - Remove empty paragraphs after <ul>. (It _seems_ this is something you would
#   always want to arrange in styling... but removing them may change vertical
#   spacing / make things inconsistent, it if there are <ul>s with and without
#   empty paragraphs below them.
c_remove_empty_paragraphs_under_blocks = True

# CUSTOM. TODO REMOVE
#if other_site:
#  c_img_bullet_re = 'posbul.?.?\.gif$'
#  c_remove_attributes['p'] = { 'margin-top': '*' }
#  c_remove_attributes['font']['face'] = ['Arial, Helvetica',  'Arial']
#  c_remove_styles['*']['line-height'].append('15.1pt')
#  c_remove_styles['*']['font-size'] = ['12pt', '3']

# About whitespace-ish stuff in the HTML document: there are different kinds:
# - <br>s. These are generally kept because they influence the output, but:
#   - A single <br> at the end of a block-level tag makes no difference and we
#     would like to remove those if possible (because a bit ugly/confusing).
#   - Two consecutive <br>s in a paragraph should be converted into two separate
#     paragraphs.
# - Regular spaces. Policy:
#   - Remove them at the end of block-level tags / <p>; they don't do anything.
#   - Also from the beginning. (A single start of a <p> does not show up in a
#     rendered document.)
#   - Further remove duplicate spaces (within most tags? not <pre>). Actually
#     this is not just 'within tags' but also if there is one space just outside
#     an 'inline' tag and one just inside, these should ideally be deduplicated.
#     - A way to do this is to move spaces at the start/end of an inline tag's
#       contents to just outside, and then de-duplicate.
# - Non-breaking spaces. Policy: dedupe _single_ non-breaking spaces which are
#   adjacent to regular spacing, just like the regular spacing (i.e. replace all
#   by a single space or newline) - if they are not at the start of a rendered
#   line. (See function startsrenderedline.)
#   - This removal actually changes the rendered document: it influences the
#     horizontal spacing between the borering elements. So maybe we don't always
#     want to do that / this should be reflected in a constant. But example MSFP
#     documents show that apparently non-breaking spaces are often inserted
#     accidentally, and therefore are better removed.
#   - We do not want to dedupe multiple &nbsp;s; we assume those are always
#     inserted on purpose.
#   - We do not want to replace standalone &nbsp;s; (surrounded by non-spaces or
#     inline tags on both sides) by normal spaces; that influences the breaking
#     of lines and we won't mess with that / will assume those are always
#     inserted on purpose.
#   We also do not want to remove them from the start of non-inline tags because
#   they make a difference there (which we assume to be intended because that's
#   visible to a Frontpage document editor); we do remove them from the end of
#   non-inline tags and just before <br>s (just like other spaces).See
#   'generally' below for inline tags.
c_dedupe_nbsp = True
# - Newlines. These have the same function as a single space in the output; they
#   are only there for formatting the HTML. Our policy:
#   - Make no assumptions about whether the HTML has any formatting. (Though we
#     know it does; most documents we've seen have plenty of newlines, even
#     empty lines.)
#   - Keep newlines after the end of block-level elements, <p> and <br>.
#   - Remove newlines from inline elements and within <p> which are not preceded
#     by <br>. (This is slightly contentious as it could remove some nice
#     formatting, however since we are shortening a lot of lines by removing
#     unnecessary style tags from a.o.<p>, it also looks strange if we keep the
#     newlines there.)
# Generally, for any of the 4 kinds of whitespace,
# - We will not leave leading/trailing whitespace inside inline tags but move
#   them just outside (for unification of the document and ease of coding some
#   logic that runs after we've done this; it does not make visible difference).
# - We will strip trailing whitespace (except newlines) at the end of non-inline
#   tags and just before <br>. They don't make a visible difference but are
#   unnecessary cruft.

### THESE REGEXES ARE REFERENCED AS A 'GLOBAL' INSIDE FUNCTIONS
#
# Regexes containing HTML tags. These can be used for matching:
# - an element that you don't know is a tag or NavigableString;
# - the full text representation of a tag.
# Should not be used on things we know are NavigableStrings, because useless,
# therefore introducing ambiguity in the code.
rxglobal_spacehmtl_only = re.compile('^(?:\s|\&nbsp\;|\<br ?\/?\>)+$')
#
# Regexes usable on NavigableStrings.
# We want to use thse for replacement (specifically by ''). Space excluding
# "&nbsp;" at the start/end of the contents of a tag don't usually influence
# formatting of the output _except_ if they are compound breaking/non-breaking
# spaces. But even if they influence only formatting of the source HTML, we
# explicitly want to 'fix' that for spaces at start/end of tag contents.
#
# To remember: NavigableStrings include newlines, and \s matches newlines.
#
# We use the fillowing for stripping whitespace (re.sub()) in some places but
# that does not need brackets.
rxglobal_newline = re.compile('\s*\n+\s*')
rxglobal_nbspace_only = re.compile('^(?:\s|\&nbsp\;)+$')
# We use the following for matching (and then modifying) the whitespace part,
# in a way that needs to access the matches in some places, so use brackets.
rxglobal_nbspace_at_start = re.compile('^((?:\s|\&nbsp\;)+)')
rxglobal_nbspace_at_end = re.compile('((?:\s|\&nbsp\;)+)$')
rxglobal_spaces_at_start = re.compile('^(\s+)')
rxglobal_multispace = re.compile('(\s{2,})')
rxglobal_multispace_at_start = re.compile('^(\s{2,})')
# Matches only a single consecutive &nbsp. (For this, the negative lookbehind
# assertion needs to contain only one character because anything else ending in
# ';' is not whitespace either.)
rxglobal_multinbspace = re.compile('((?:\s|(?<!\;)\&nbsp\;(?!\&nbsp\;)){2,})')
rxglobal_multinbspace_at_start = re.compile('^((?:\s|(?<!\;)\&nbsp\;(?!\&nbsp\;)){2,})')
# The first negative lookbehind assertion for "not at the start of the string",
# (which amounts to explicitly matching a non-space character which is not the
# ; in &nbsp;,) is unfortunate. Because now, for doing re.sub(), we need to
# explicitly put \1 back into the replacement string.
rxglobal_multinbspace_not_at_start = re.compile('(\S)(?<!\&nbsp\;)((?:\s|(?<!\;)\&nbsp\;(?!\&nbsp\;)){2,})')

###
### Functions 1/3: helper functions which are pretty much general
###

# Return the index of an element inside parent contents.
def getindexinparent(slf):
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

# Return the tag name of an element (or '' if this is not a tag).
#
# I was surprised I can't find a function like this in BS...
def gettagname(element):
  if element.__class__.__name__ != 'Tag':
    return ''
  m = saferegexsearch(element.__repr__(), re.compile('^\<([^\ >]+)'))
  if m:
    return m.group(1)
  return ''

# Move all contents out of one tag, to just before another tag.
def movecontentsbefore(fromwithin, tobefore):
  movecontentsinside(fromwithin, tobefore.parent, getindexinparent(tobefore))

# Move all or some (last part of) contents out of one tag, to inside another tag
# (at a specified index; default at the start).
def movecontentsinside(fromwithin, toinside, insertindex = 0, fromindex = 0):
  r = fromwithin.contents
  i = insertindex
  while len(r) > fromindex:
    # We are assuming that Beautifulsoup itself starts out having maximum one
    # consecutive NavigableString within a tag. It's easy to write code which
    # inadvertantly assumes this is always the case. The below if/elif can be
    # deleted, but they ease the adverse effect that such buggy code would have.
    # Still, it's only a part solution / such code is considered buggy. Because
    # every tag.extract() command could leave two consecutive NavigableStrings
    # behind; there's nothing preventing that.
    # Tip for tracing such buggy code: (un)comment all from the 'if' to 'else:'
    # and re-run the script. The output should be the same.
#    if i > 0 and r[fromindex].__class__.__name__ == 'NavigableString' and toinside.contents[i-1].__class__.__name__ == 'NavigableString':
      # Append the string to be inserted, to the string appearing right before
      # the destination. (Even though we always check this, this condition
      # should only be true when inserting the first element.)
#      toinside.contents[i-1].replaceWith(str(toinside.contents[i-1]) + str(r[fromindex]))
#      r[fromindex].extract()
#    elif len(r) == fromindex + 1 and i < len(toinside.contents) and r[fromindex].__class__.__name__ == 'NavigableString' and toinside.contents[i].__class__.__name__ == 'NavigableString':
      # Prepend the last string to be inserted to the string appearing right
      # after the destination (i.e. at the destinaton's index).
#      toinside.contents[i].replaceWith(str(r[fromindex]) + str(toinside.contents[i]))
#      r[fromindex].extract()
#    else:
      toinside.insert(i, r[fromindex])
      i = i + 1

# Check if element matches regex; 'safe' replacement for rx.search(str(e))
# where no error will be thrown regardless whether element is a tag or
# NavigableString.
def saferegexsearch(element, rx):
  # Difficulty here: str(ee) may give UnicodeEncodeError with some characters
  # and so may ee.__str__() and repr(ee) (the latter with some \x?? chars).
  # The only thing sure to not give errors is ee.__repr__()
  # However you don't want to use THAT for matching! So use it as a safety net
  # to make sure str() is not called when unicode chars are in there
  #
  # Yeah, I know, it's probably just my limited Python knowledge, that made me
  # write this function...
  # (If it isn't a bug in BeautifulSoup 3.1; probably not.)
  s = element.__repr__()
  if s.find('\\u') != -1 or s.find('\\x') != -1:
    return False
  return rx.search(str(element))

# Get filtered contents of a tag.
#
# This exists for making code easier to read (by extracting the lambda from it)
# and easier to remember (i.e. the difference between t.findAll and t.contents)
def getcontents(tag, contents_type):
  if contents_type == 'nonwhitespace_string':
    # Return non-whitespace NavigableStrings.
    return tag.findAll(text=lambda x, r=rxglobal_nbspace_only: r.match(x)==None, recursive=False)
  elif contents_type == 'tags':
    return tag.findAll(recursive=False)
  # Default, though we're probably not going to call the function for this:
  return tag.contents

# Determines if an element is on the beginning of a rendered line.
#
# This function assumes that all existing inline tags have non-whitespace
# contents and all non-inline elements take up the full vertical space for
# themselves (i.e. they start at a new line, and the content directly after them
# does too).
def startsrenderedline(element, inline_tagnames = []):
  # If a previous element exists within the same parent, assume we're at the
  # start of a line if the element is non-inline, and we're not at the start
  # if the element is inline. (See assumption above.)
  previous = element.previousSibling
  while previous == None:
    # If we're at the start of an inline tag, keep looking outside that tag.
    # If we're at the start of another tag, assume we're at the start of a line.
    if not (gettagname(element.parent) in inline_tagnames):
      at_line_start = True
      break
    # We also assume we will never get here with the very first element in the
    # document (because there's always a <head> which breaks this loop).
    element = element.parent
    previous = element.previousSibling

  if previous != None:
    n = gettagname(previous)
    at_line_start = not(n == '' or n in inline_tagnames)
  return at_line_start

# De-duplicate whitespace in NavigableString.
#
# Later adjacent NavigableStrings get merged into the provided one if possible.
# We determine if the string always gets rendered at the start of a line, and
# adjust for this in the de-duplication of non-breaking whitespace & the
# keeping of a newline as the deduped string.
def dedupewhitespace(navstr, inline_tagnames = ['strong', 'em', 'font', 'span', 'a']):
  at_line_start = startsrenderedline(navstr, inline_tags)
  s = str(navstr)
  # Merge consecutive strings.
  nexttag = navstr.nextSibling
  while nexttag != None and r[i + 1].__class__.__name__ == 'NavigableString':
    s += str(nexttag)
    nexttag.extract()
    nexttag = navstr.nextSibling

  # Dedupe spaces at start of our string.
  # - Replace single &nbsp;s too, unless our constant says not to OR our string
  #   is at the start of a rendered line.
  # - Replace _by_ single space, unless the string includes a newline and is at
  #   the start of a rendered line.
  rx = rxglobal_multinbspace_at_start if c_dedupe_nbsp and not at_line_start else rxglobal_multispace_at_start
  m =  rx.search(s)
  if m:
    replacement = '\n' if m.group(1).find('\n') != -1 and at_line_start else ' '
    # This sub() does not need restrictions because we know it replaces maximum
    # one occurrence.
    s = rx.sub(replacement, s)

  # Dedupe spaces elsewhere in our string. Since we won't touch the very start
  # of our string anymore, the replacement is never '\n'.
  if c_dedupe_nbsp and at_line_start:
    # We want to deduplicate &nbsp;s too, but not those wich occur in whitespace
    # at the very start of our string. (We just explicitly prevented replacing
    # those, above.) We have a special regex for this. We should be able to
    # just replace all occurrences with one command (like in the 'else' below)
    # but \1 does not seem to work as replacement? So loop and replace one by
    # one.
    m = saferegexsearch(s, rxglobal_multinbspace_not_at_start)
    while m:
      s = rxglobal_multinbspace_not_at_start.sub(m.group(1) + ' ', s, 1)
      m = saferegexsearch(s, rxglobal_multinbspace_not_at_start)
  else:
    # Deduplicate single &nbsp;s too, unless our constant says not to OR we've
    # already just done it.
    rx = rxglobal_multinbspace if c_dedupe_nbsp else rxglobal_multispace
    s = rx.sub(' ', s)

  if s != str(navstr):
    navstr.replaceWith(s)

# Strip whitespace from the start of a NavigableString.
#
# If the whole string is whitespace (also if that is non-breaking), then
# remove the NavigableString and repeat the stripping if the next sibling
# is also a NavigableString. Stop if any tag is encountered (including <br>).
#
# <br> and &nbsp; have effect at the start of a string so do not remove them; do
# not look behind &nbsp;, because
# - a single space after &nbsp; does have effect so it should not be stripped;
# - there is other code to dedupe spaces. We strip but don't dedupe.
#
# If newlines are found, keep one at most.
def stripleadingwhitespace(navstr):
  readd_newline = False
  m = saferegexsearch(navstr, rxglobal_spaces_at_start)
  while m:
    replacement = '' if navstr.find('\n') == -1 else '\n'
    if m.group(1) == str(navstr):
      # NavigableString contains only whitespace, fully being removed. We need
      # to loop back and check again. Also, if we encountered a newline then add
      # at most one back at the start.
      nxt = navstr.nextSibling
      navstr.extract()
      navstr = nxt
      if len(replacement):
        readd_newline = True
      m = None
      if navstr != None and navstr.__class__.__name__ == 'NavigableString':
        m = saferegexsearch(navstr, rxglobal_spaces_at_start)
    elif replacement != m.group(1):
      # String is only part whitespace: strip/replace it and be done.
      # Handle the adding-of-newlines here.
      if readd_newline:
        replacement = '\n'
      # If replacement is already '\n', don't add an extra one.
      if len(replacement):
        readd_newline = False
      s = str(navstr)
      navstr.replaceWith(replacement + s[ len(m.group(1)) : ])
      m = None
    else:
      # replacement == '\n' and navstr starts with a single newline followed by
      # a non-space. (Because replacement == '' will always be matched by the
      # 'elif'.) Don't loop, and don't bother checking about the \n.
      m = None
      readd_newline = False
  if readd_newline:
    # As noted: re-add newline unless NavigableString starts with newline.
    # (Actually 'starts with newline' can never be true here, but w/e.)
    if navstr == None:
      e = NavigableString('\n')
      navstr.parent.insert(0, e)
    elif navstr.__class__.__name__== 'Tag':
      e = NavigableString('\n')
      navstr.parent.insert(getindexinparent(navstr), e)
    else:
      navstr.replaceWith('\n' + str(navstr))

# Strip whitespace from the end of a NavigableString.
#
# If the whole string is whitespace (also if that is non-breaking), then
# remove the NavigableString and repeat the stripping if the previous sibling
# is also a NavigableString. Stop if any tag is encountered (including <br>).
#
# If readd_newline is True, then add at most one newline back to the end of the
# stripped element
def striptrailingwhitespace(navstr, readd_newline = False):
  m = saferegexsearch(navstr, rxglobal_nbspace_at_end)
  while m:
    replacement = '' if navstr.find('\n') == -1 else '\n'
    if m.group(1) == str(navstr):
      # NavigableString contains only whitespace, fully being removed. We need
      # to loop back and check again. Also, if we encountered a newline then add
      # at most one back at the end.
      prev = navstr.previousSibling
      navstr.extract()
      navstr = prev
      if len(replacement):
        readd_newline = True
      m = None
      if navstr != None and navstr.__class__.__name__ == 'NavigableString':
        m = saferegexsearch(navstr, rxglobal_nbspace_at_end)
    elif replacement != m.group(1):
      # String is only part whitespace: strip/replace it and be done.
      # Handle the adding-of-newlines here.
      if readd_newline:
        replacement = '\n'
      # If replacement is already '\n', don't add an extra one.
      if len(replacement):
        readd_newline = False
      s = str(navstr)
      navstr.replaceWith(s[ : -len(m.group(1))] + replacement)
      m = None
    else:
      # replacement == '\n' and navstr ends with a non-space followed by a
      # single newline. (Because replacement == '' will always be matched by the
      # 'elif'.) Don't loop, and don't bother checking about the \n.
      m = None
      readd_newline = False
  if readd_newline and navstr != None:
    # As noted: re-add newline unless NavigableString ends in newline. (And
    # unless tag contents are now empty.)
    if navstr.__class__.__name__== 'Tag':
      e = NavigableString('\n')
      navstr.parent.insert(getindexinparent(navstr) + 1, e)
    else:
      s = str(navstr)
      if s[-1] != '\n':
        navstr.replaceWith(s + '\n')

# Remove whitespace from start / end of a tag's contents.
#
# This should not be done for inline tags. It assumes:
# - We don't need to recurse into child tags (because we already handled those).
# - Our contents could be only whitespace/<br>. In that case we still won't
#   remove the empty tags; they might still mean something (because of being
#   a non-inline tag, possibly having an 'id' or whatever else).
def stripnoninlinewhitespace(tag):
  # We really should not have empty contents by now, but still:
  r = tag.contents
  if len(r):
    # Strip whitespace from end. Assume:
    # - There can be multiple NavigableStrings before the end of the tag.
    # - If the last encountered tag is <br>, we don't need to look further
    #   before it, because other code will do that. ( / has done that.)
    # - One <br> at the end of a non-inline tag does not do anything in the
    #   rendered document, so we should remove it.
    # - Any &nbsp;: same.
    readd_newline = False
    if r[-1].__class__.__name__== 'Tag' and gettagname(r[-1]) == 'br':
      r[-1].extract()
    elif saferegexsearch(r[-1], rxglobal_nbspace_only) and len(r) > 1 and r[-2].__class__.__name__ == 'Tag' and gettagname(r[-2]) == 'br':
      # Remove both the spaces and this one <br>, then check the next. If there
      # was a newline somewhere after the <br> then add that after the last
      # remaining tag/string - except if the string already ends in a newline.
      readd_newline = r[-1].find('\n') != -1
      r[-1].extract()
      r[-1].extract()
    # Now strip (more) spaces from the end of the last NavigableString(s), but
    # no (more) <br>. (If the tag is now totally empty, don't readd newline.)
    if len(r):
      striptrailingwhitespace(r[-1], readd_newline)
      # Also strip from the start.
      if len(r):
        stripleadingwhitespace(r[0])

# Move leading/trailing whitespace out of tag; optionally remove empty tag.
#
# This function's logic is suitable for inline tags only. We assume that all
# kinds of whitespace may be moved outside inline tags, without this influencing
# formatting of the output. This includes both newlines (influencing formatting
# of the source HTML; we assume we never need newlines to stay just before
# inline-end tags) and <br>s.
#
# We do not want to end up inserting whitespace at the very beginning/end of
# an inline tag. That is: if our tag is e.g. at the very end of its parent,
# we don't want to move whitespace out into it(s end) - but rather into a
# further ancestor tag. (Otherwise the end result would depend on which tags
# we process before others.) The second argument contains all the inline tag
# names for doing the "never insert whitespace at the very beginning/end" check.
def movewhitespacetoparent(tag, remove_if_empty = True, inline_tagnames = []):
  r = tag.contents
  # Remove tags containing nothing.
  if len(r) == 0:
    if remove_if_empty:
      tag.extract()
    return

  # Move all-whitespace contents (including <br>) to before. This could change
  # r, so loop.
  while saferegexsearch(r[0], rxglobal_spacehmtl_only):
    # Find destination tag, and possibly destination string, to move our
    # whitespace to.
    t = tag
    while t.previousSibling == None and gettagname(t.parent) in inline_tagnames:
      # Parent is inline and we'd be inserting whitespace at its start: continue
      # to grandparent.
      t = t.parent
    dest_tag = t.parent
    possible_dest = t.previousSibling

    # Move full-whitespace string/tag to its destination.
    if r[0].__class__.__name__ == 'Tag' or possible_dest.__class__.__name__ != 'NavigableString':
      # Move tag or full NavigableString into destination tag, either after the
      # previous sibling or (if that does not exist) at the start. (The insert()
      # command will implicitly remove it from its old location.)
      dest_index = getindexinparent(possible_dest) + 1 if possible_dest else 0
      dest_tag.insert(dest_index, r[0])
    else:
      # Prepend to existing string.
      possible_dest.replaceWith(str(possible_dest) + str(r[0]))
      # Remove existing NavigableString.
      r[0].extract()
    if not r:
      if remove_if_empty:
        tag.extract()
      return

  # Move whitespace part at start of NavigableString to before tag.
  m = saferegexsearch(r[0], rxglobal_nbspace_at_start)
  if m:
    # Find destination tag/string to move our whitespace to.
    t = tag
    while t.previousSibling == None and gettagname(t.parent) in inline_tagnames:
      t = t.parent
    dest_tag = t.parent
    possible_dest = t.previousSibling

    # Move whitespace string to its destination.
    if possible_dest.__class__.__name__ != 'NavigableString':
      # Insert new NavigableString into destination tag,either after the
      # previous sibling or (if that does not exist) at the start.
      e = NavigableString(m.group(1))
      dest_index = getindexinparent(possible_dest) + 1 if possible_dest else 0
      dest_tag.insert(dest_index, e)
    else:
      # Append to existing NavigableString.
      possible_dest.replaceWith(str(possible_dest) + m.group(1))

    # Remove whitespace from the existing NavigableString.
    len_whitespace = len(m.group(1))
    s = str(r[0])
    r[0].replaceWith(s[len_whitespace : ])

  # Move all-whitespace contents (including <br>) to after. This could change
  # r, so loop. Because of above, we know r will never become empty here.
  while saferegexsearch(r[-1], rxglobal_spacehmtl_only):
    # Find destination tag, and possibly destination string, to move our
    # whitespace to.
    t = tag
    while t.nextSibling == None and gettagname(t.parent) in inline_tagnames:
      # Parent is inline and we'd be inserting whitespace at its end: continue
      # to grandparent.
      t = t.parent
    dest_tag = t.parent
    possible_dest = t.nextSibling

    # Move full-whitespace string/tag to its destination.
    if r[-1].__class__.__name__ == 'Tag' or possible_dest.__class__.__name__ != 'NavigableString':
      # Move tag or full NavigableString into destination tag, either before the
      # next sibling or (if that does not exist) at the end. (The insert()
      # command will implicitly remove it from its old location.)
      dest_index = getindexinparent(possible_dest) if possible_dest else len(dest_tag.contents)
      dest_tag.insert(dest_index, r[-1])
    else:
      # Prepend to existing string.
      possible_dest.replaceWith(str(r[-1]) + str(possible_dest))
      # Remove existing NavigableString.
      r[-1].extract()

  # Move whitespace part at end of NavigableString to after tag.
  m = saferegexsearch(r[-1], rxglobal_nbspace_at_end)
  if m:
    # Find destination tag/string to move our whitespace to.
    t = tag
    while t.nextSibling == None and gettagname(t.parent) in inline_tagnames:
      t = t.parent
    dest_tag = t.parent
    possible_dest = t.nextSibling

    # Move whitespace string to its destination.
    if possible_dest.__class__.__name__ != 'NavigableString':
      # Insert new NavigableString into destination tag, either before the next
      # sibling or (if that does not exist) at the end.
      e = NavigableString(m.group(1))
      dest_index = getindexinparent(possible_dest) if possible_dest else len(dest_tag.contents)
      dest_tag.insert(dest_index, e)
    else:
      # Prepend to existing NavigableString.
      possible_dest.replaceWith(m.group(1) + str(possible_dest))

    # Remove whitespace from the existing NavigableString.
    len_whitespace = len(m.group(1))
    s = str(r[-1])
    r[-1].replaceWith(s[ : -len_whitespace])


# Get style attribute from tag, return it as dictionary. Keys always lowercase.
def getstyles(t):
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
    s = getstyles(t)
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
  if gettagname(t) != 'img':
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
  r = getcontents(pe, 'nonwhitespace_string')
  if len(r):
    # Setting 'inherit' effectively means: prevent parent's alignment from being changed.
    al['inherit'] = True

  ## Find/index alignment of all tags within pe, and process them.
  for t in pe.findAll(recursive=False):

    tagname = gettagname(t)
    talign = getalign(t)
    if talign:
      thisalign = talign
      allowchange = 'any'
    elif tagname == 'center':
      thisalign = 'center'
      allowchange = parentalign
    else:
      thisalign = parentalign
      if tagname == 'p':
        allowchange = 'any'
      else:
        allowchange = ''

    # Recurse through subelements first.
    tal = checkalign(t, thisalign, allowchange)
    # Handling of 'implicitly aligning tags', i.e. <center>:
    if tagname == 'center':
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
# This is, and must remain, dempotent. mangletag() may call it multiple times.
def mangleattributes(tag):
  tagname = gettagname(tag)
  # tag.attrs is list of tuples, so if you loop through it, you get tuples back.
  # Still you can _use_ it as a dict type. So you can assign and delete stuff by
  # key, however you may not delete attributes from the tag by key while
  # iterating over its .attrs list! That makes the iterator break off. So
  # create a list of keys first.
  attr_names = []
  for attr in tag.attrs:
    attr_names.append(attr[0])
  for orig_name in attr_names:
    orig_value = tag.get(orig_name)
    name = orig_name.lower()
    value = orig_value.lower()

    # Check if we should remove this attribute.
    remove = False
    if tagname in c_remove_attributes and name in c_remove_attributes[tagname]:
      if isinstance(c_remove_attributes[tagname][name], list):
        remove = value in c_remove_attributes[tagname][name]
      else:
        remove = c_remove_attributes[tagname][name] in [value, '*']
    elif '*' in c_remove_attributes and name in c_remove_attributes['*']:
      if isinstance(c_remove_attributes['*'][name], list):
        remove = value in c_remove_attributes['*'][name]
      else:
        remove = c_remove_attributes['*'][name] in [value, '*']
    if remove:
      value = ''

    elif name == 'align':
      # Replace deprecated align attribute by newer way. Unlike the below,
      # this call already resets the 'align' attribute itself, so we do not
      # reset 'value', in order to skip the below code which changes attributes.
      setalign(tag, value)

    elif name == 'class':
      classes = orig_value.split()
      for value in classes:
        if value.lower() == 'msonormal':
          classes.remove(value)
      value = ' '.join(classes)

    elif name == 'style':
      # Loop over style name/values; rebuild the attribute value from scratch.
      styledefs = orig_value.split(';')
      value = ''
      for s in styledefs:
        if s.strip() != '':
          (sn, sv) = s.split(':', 1)
          sn = sn.strip()
          sv = sv.strip()
          # We want to keep case of style name/values but not for comparison.
          lsn = sn.lower()
          lsv = sv.lower()

          # Check if we should remove this style.
          remove = False
          if tagname in c_remove_styles and lsn in c_remove_styles[tagname]:
            if isinstance(c_remove_styles[tagname][lsn], list):
              remove = lsv in c_remove_styles[tagname][lsn]
            else:
              remove = c_remove_styles[tagname][lsn] in [lsv, '*']
          elif '*' in c_remove_styles and lsn in c_remove_styles['*']:
            if isinstance(c_remove_styles['*'][lsn], list):
              remove = lsv in c_remove_styles['*'][lsn]
            else:
              remove = c_remove_styles['*'][lsn] in [lsv, '*']
          if remove:
            sv = ''

          elif sn.startswith('margin'):
            # Always remove small margins.
            if sv.isnumeric() and float(sv) < 0.02:
              sv = ''

          elif sn.startswith('mso-'):
            # Weird office specific styles? Never check, just delete and hope
            # they didn't do anything.
            sv = ''

          # Re-add the style value, unless we discarded it.
          if sv:
            if value != '':
              value += '; '
            value += sn + ': ' + sv

    # Check if attributes have changed (but don't change case only); always
    # change attribute names to lower case.
    if name != orig_name or value != orig_value.lower():
      if name != orig_name or not value:
        del tag[orig_name]
      if value:
        tag[name] = value


# Try to move all attributes out of the current tag (into parent or only child);
# if this is possible or the tag has no attributes, remove the tag. This can
# also change/delete attributes.
#
# This can be used to remove 'purely inline' (non-'position') tags. There is
# special handling for:
# - <font> which we always want to remove: if we cannot move all its attributes
#   somewhere else then we replace it by a <span>.
# - <a> which only hold a name; we replace it by an id in another tag if that
#   doesn't have one yet.
def mangletag(tag):
  dest = None
  dest_is_child = False
  dest_is_new = False

  tagname = gettagname(tag)
  # Do pre-check for <a> to prevent needless processing: we only process
  # non-'href' tags with a name attribute and no id. (Tags without href _or_
  # name are strange enough to leave alone.)
  if tagname == 'a' and (not tag.get('name') or tag.get('id') or tag.get('href')):
    return

  # Decide which is going to be the 'destination' tag, where we will move any
  # style attributes to:
  #
  # Check for single child element which can hold style attributes. (It seems
  # like this is preferred over a parent element, because we prefer putting
  # styles in the most specific one.) Note we will also match 'position' tags
  # even though they should never be found inside 'inline' tags; if this ever
  # happens, then we will surely want to get rid of the 'inline' tag.
  # Find child non-space NavigableStrings(?): should find nothing.
  r1 = getcontents(tag, 'nonwhitespace_string')
  if len(r1) == 0:
    # Find child tags: should find one tag.
    r1 = getcontents(tag, 'tags')
    if len(r1) == 1:
      name = gettagname(r1[0])
      if name in ['a', 'p', 'span', 'div', 'h2', 'h3', 'h4', 'li', 'blockquote']:
        # A last deal breaker is if both tag and the destination have an id.
        if not (tagname == 'a' or tag.get('id') and r1[0].get('id')):
          dest = r1[0]
          dest_is_child = True
  if dest is None:
    # Check for parent element which can hold style attributes, and where the
    # tag is the only child - except for 'a' which is allowed to have siblings.
    parent_tag = tag.parent
    name = gettagname(parent_tag)
    # (XHTML specified that blockquote must contain block-level elements. No
    # more; in HTML it may contain just text.)
    if name in ['a', 'p', 'span', 'div', 'h2', 'h3', 'h4', 'li', 'blockquote']:
      r1 = getcontents(parent_tag, 'tags')
      if len(r1) == 1:
        r1 = getcontents(parent_tag, 'nonwhitespace_string') if tagname != 'a' else []
        if len(r1) == 0:
          if not ((tagname == 'a' or tag.get('id')) and parent_tag.get('id')):
            dest = parent_tag

  if dest is None:
    if tagname == 'font':
      # Cannot use a direct parent/child. Make new <span> to replace the <font>.
      # This could be weird in theory; there could be a font tag surrounding one
      # or several block-level elements; putting a span there is frowned upon,
      # if not illegal. However, leaving a 'font' tag is probably equally bad...
      # For the moment, we are just hoping that we have cleaned up all font tags
      # where this is the case, above.
      dest = Tag(soup, 'span')
      parent_tag.insert(getindexinparent(tag), dest)
      dest_is_new = True
    else:
      # We cannot merge this tag into another one, but we'll also change
      # attributes here if necessary.
      mangleattributes(tag)
      # If the tagname itself has no implicit meaning, remove it. (The <div>
      # is disputable; it's not 100% sure that removing an empty one will not
      # influence positioning/grouping. But we assume for MS Frontpage pages
      # they are superfluous. See also: comments at caller.)
      if len(tag.attrs) == 0 and tagname in ['span', 'div']:
        movecontentsbefore(tag, tag)
        tag.extract()
      return

  # Before we merge attributes, normalize their names/values.
  mangleattributes(dest)
  merge_classes = ''
  merge_styles = {}
  # Get the attributes (excl. style) and styles to merge into destination.
  if tagname == 'font':
    # Iterate over attributes and convert them all into styles; don't move any
    # attributes as-is. (Note: you get attributes as a list of tuples.)
    # We may not delete attributes from the tag by key while iterating over its
    # .attrs list; that makes the iterator break. Create a list of keys first.
    attr_names = []
    for attr in tag.attrs:
      attr_names.append(attr[0])
    for can in attr_names:
      an = can.lower()
      av = t.get(can)
      sn = ''

      # Check if we should remove this attribute.
      remove = False
      if 'font' in c_remove_attributes and an in c_remove_attributes['font']:
        if isinstance(c_remove_attributes['font'][an], list):
          remove = av in c_remove_attributes['font'][an]
        else:
          remove = c_remove_attributes['font'][an] in [value, '*']
      elif '*' in c_remove_attributes and an in c_remove_attributes['*']:
        if isinstance(c_remove_attributes['*'][an], list):
          remove = av in c_remove_attributes['*'][an]
        else:
          remove = c_remove_attributes['*'][an] in [value, '*']
      if remove:
        # Fall through but also remove the tag, for the len() check.
        del tag[an]

      elif an == 'color':
        sn = 'color'
      elif an == 'face':
        sn = 'font-family'
      elif an == 'size':
        sn = 'font-size'

      if sn:
        del tag[an]
        merge_styles[sn] = av

    # Since the font tag has only above 3 possible attributes, it should be
    # empty now. If it's not, we should re-check the code below to see whether
    # things are
    if len(tag.attrs) != 0:
      exit('font end tag without start tag found at pos ' + str(pe))
    # We have not checked whether merge_styles contain unneeded attributes; we
    # will 'mangle' the new tag again after merging the styles into the
    # destination tag. Also, unlike the 'else:' block below we don't check if
    # there are styles to merge ours _into_.

  else:
    mangleattributes(tag)
    # Styles and classes need to be merged into the destination tag, if that
    # already has these attributes. If not, just move/merge the whole attribute
    # along with the others.
    if dest.get('style'):
      merge_styles = getstyles(tag)
    if dest.get('class'):
      merge_classes = tag.get('class')


  # Merge the attributes into the destination.
  for attr in tag.attrs:
    # One special case: <a name> becomes id. We've checked duplicates already.
    dest_name = attr[0] if (tagname != 'a' or attr[0] != 'name') else 'id'
    # Overwrite the value into the destination, except if:
    # - the destination is the child, which has the same attribute; then skip.
    # - the destination also has the 'style/class' attribute; then merge below.
    dest_value = dest.get(dest_name)
    if not (dest_value and (dest_is_child or attr[0] in ['style', 'class'])):
      dest[dest_name] = attr[1]

  # Merge classes into the destination.
  if merge_classes:
    # We know destination classes exist.
    classes = set(
      map(str.lower, re.split('\s+', dest.get('class')))
    ).union(set(
      map(str.lower, re.split('\s+', merge_classes))
    ))
    dest['class'] = ' '.join(classes)

  # Merge styles into the destination.
  if merge_styles:
    dest_styles = getstyles(dest)
    for name in merge_styles:
      # If the destination already has the style: overwrite child value into
      # parent, or skip if the destination is the child.
      if not (dest_is_child and name in dest_styles):
        dest_styles[name] = merge_styles[name]
    # Reconstruct the style and put it back into the destination element.
    s = ''
    for name in dest_styles:
      if s != '':
        s += '; '
      s += name + ': ' + dest_styles[name]
    dest['style'] = s

  # Now move the old tag content and remove the tag.
  if dest_is_new:
    movecontentsinside(tag, dest)
  else:
    # Move everything into the parent, just before the tag. (If the destination
    # is the child tag, "everything" includes the destination.)
    movecontentsbefore(tag, tag)
  tag.extract()

  # It is possible that some styles that we copied from the font tag are not
  # needed. In order to not have to change more code: check destination again.
  if tagname == 'font':
    mangleattributes(dest)


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
# Clean up completely wrong HTML before parsing - #1:
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
#
# This is a bit arbitrary because it only strips font tags with _only_ the
# 'face' attribute. For better or worse, we so far are assuming that these are
# the only "completely wrong" tags, and others can/will be handled by
# BeautifulSoup (stripped/converted to spans if necessary) later.
if 'font' in c_remove_attributes and 'face' in c_remove_attributes['font']:
  if isinstance(c_remove_attributes['font']['face'], list):
    font_families = c_remove_attributes['font']['face']
  else :
    font_families = [c_remove_attributes['font']['face']]

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
# Clean up completely wrong HTML before parsing - #2:
#
# Solve <b><p > .... </b> ... </p> by putting <b> inside <p>. (If we don't,
# BeatifulSoup will put a </p> before the </b> which will mess up formatting.)
rx1 = re.compile('\<b\>(\s*\<p.*?\>)(.*?)\<\/b>', re.S)
for r in rx1.finditer(html):
  if r.group(2).find('/p>') == -1:
    html = html[:r.start()] + r.group(1) + '<b>' + html[r.start(2):]
    # since html stays just as long, the finditer will be OK?

##############
###
### Now do the tidying work, using BeautifulSoup.

soup = BeautifulSoup(html)

## Soup part 1: remove some structural things, and unify for compliant
## HTML.

# Delete all script tags.
r = soup.findAll('script')
[e.extract() for e in r]

# Delete comments; we assume we never want to keep MS Frontpage comments.
r = soup.findAll(text=lambda text:isinstance(text, Comment))
[e.extract() for e in r]

# Replace b->strong and i->em, for XHTML compliance, and so that we're sure we
# are not skipping tags in the code below
for t in soup.findAll('b'):
  e = Tag(soup, 'strong')
  t.parent.insert(getindexinparent(t), e)
  movecontentsinside(t, e)
  t.extract()
for t in soup.findAll('i'):
  e = Tag(soup, 'em')
  t.parent.insert(getindexinparent(t), e)
  movecontentsinside(t, e)
  t.extract()

# Remove strange MSFT 'o:p' tags.
#
# We have no idea what they are useful for; they're sometimes inserted in random
# places in the middle of a sentence inside a span, don't always have end tags.
# Let's get rid of them and dedupe any spacing later.
for t in soup.findAll('o:p'):
  r = t.contents
  if len(r):
    movecontentsbefore(t, t)
  t.extract()


## Soup part 2: work on large block elements in document structure.

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
      t.parent.insert(getindexinparent(t), e)
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
    l = getindexinparent(t)
    t.parent.insert(l, e)
    # insert li's and move all the contents from the second td's into there
    # (Is it always legal to just 'dump everything' inside a li? Let's hope so.)
    i = 0
    for tr in r_tr:
      ee = Tag(soup,'li')
      e.insert(i, ee)
      r_td = tr.findAll('td', recursive=False)
      #r_cont = r_td[1].findAll()
      # In the preceding code we used findAll() because we assumed that there
      # are no loose NavigableStrings in between tr's or td's.
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
      ee = NavigableString('\n')
      e.insert(i + 1, ee)
      i = i + 2
    t.extract()


# Delete/change superfluous alignment attributes (and <center> tags sometimes)
checkalign(soup.body, 'left')


## Soup part 3: change/remove/unify contents of non-'large block' tags.
#
# Generally try to unify stuff before removing/changing stuff.

# Some 'a' tags have 'strong' tags surrounding them, and some have 'strong' tags
# inside them. Normalize this so that 'a' is always inside.
r = soup.findAll('a')
for t in r:
  r1 = t.findAll('strong', recursive=False)
  if r1:
    r2 = t.findAll(recursive=False)
    if len(r1) == len(r2) and len(getcontents(t, 'nonwhitespace_string')) == 0:
      # all tags are 'strong' and all navigablestrings are whitespace.
      # Delete the 'strong' (can be a chain of multiple, in extreme weird cases)
      for e in r1:
        movecontentsbefore(e, e)
        e.extract()
      # make 'strong' tag and move e inside it
      e = Tag(soup, 'strong')
      t.parent.insert(getindexinparent(t), e)
      e.insert(0, t)
# Maybe TODO: have a class for 'strong' links? That would remove the need for:
# Links are rendered in bold, by default.
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

inline_tags = ['strong', 'em', 'font', 'span', 'a'];

# Move leading/trailing whitespace out of inline tags into parents; remove empty
# tags.
#
# This could be useful to do before mangletag() stuff, because then we don't
# have to deal with attributes inside these empty tags; they will just be
# removed. We assume these inline tags don't contain attributes like 'id' which
# must be preserved. (This is why we won't do 'div' and 'a' here. These could be
# processed despite not being pure-inline tags, but only if they don't have an
# 'id', and preferrably after mangletag(). But right now we won't; it seems too
# much trouble for little/no gain.)
for tagname in inline_tags:
  for t in soup.findAll(tagname):
    movewhitespacetoparent(t, tagname != 'a', inline_tags)

# Check if we can get rid of some 'inline' (not 'positioning') tags if we move
# their attributes to a child/parent; also normalize their attributes. <font>
# must come first; it has special handling so it's always removed (and replaced
# by <span> if necessary). We're not sure of what definition we adhere to yet:
# - <div> is not an inline element but we assume we can remove it for MS
#   Frontpage pages without trouble. (If this turns out not to be the case, we
#   might need to change checkalign() because that may leave empty <div>s
#   around which are in fact unnecessary.)
# - <p> is also not an inline element, but we assume we can remove it if it is
#   the single tag wrapped in another element (like e.g. blockquote, li). (Or
#   wrapping a single other element, but that probably won't happen.) We must
#   leave it at the end though, because we want other tags to be removed in
#   favor of <p>. Also we want to remove spacing in paragraphs before dong this.
for tagname in ['font', 'div', 'span', 'a']:
  for t in soup.findAll(tagname):
    mangletag(t)
# Normalize other tags' attributes if necessary.
#
# (h2 / h4 tags with cleanable attributes found in one website. Adding h3.)
for tagname in ['p', 'h2', 'h3', 'h4']:
  for t in soup.findAll(tagname):
    mangleattributes(t)

# Now that spacing is moved to where it should be and unnecessary tags are gone:

# Remove duplicate spacing and unnecessary newlines.
#
# This implies first concatenating any adjacent NavigableStrings (which can
# occur since we've extract()ed tags).
#
# Remove newlines except if the string is at the start of a rendered line. (This
# includes newlines inside <p>s; see newline policy. Also we've seen e.g. h2
# tags with two newlines in the middle of the title so we explicitly want to do
# those.) We won't recurse into child tags; we don't dare to assume that no tags
# will have problems with whitespace removal - e.g. <pre>.)
for tagname in inline_tags + ['p', 'h2', 'h3', 'h4', 'li']:
  for t in soup.findAll(tagname):
    r = t.contents
    i = 0
    while i < len(r):
      # Skip to next string.
      if r[i].__class__.__name__ == 'NavigableString':
        # This may shorten r, but does not extract r[i].
        dedupewhitespace(r[i], inline_tags)
      i += 1

# Remove unnecessary whitespace at start/end of non-inline tags.
#
# This does not make a difference for rendering; it just makes for neater HTML.
# (We've often seen useless &nbsp;s at the end of lines (li/p) which are just
# ugly. We just do the rest too because why not.)
for tagname in ['p', 'h2', 'h3', 'h4', 'li', 'div']:
  for t in soup.findAll(tagname):
    stripnoninlinewhitespace(t)
stripnoninlinewhitespace(soup.body)

# In the same vein, remove unnecessary whitespace just before and after <br>s.
#
# This is partly duplicate because most NavigableStrings around <br> have
# been processed by the previous code block. This also does <br>s that are
# not inside (the first level of) the tags specified just above.
for t in soup.findAll('br'):
  e = t.previousSibling
  if e != None and e.__class__.__name__ == 'NavigableString':
    striptrailingwhitespace(e)
  e = t.nextSibling
  if e != None and e.__class__.__name__ == 'NavigableString':
    stripleadingwhitespace(e)

# When inside a paragraph, replace (exactly) two consecutive <br>s by a
# paragraph ending + start.
#
# (This is also 'unifying HTML' so more like 'Soup part 1', but we prefer doing
# this after movewhitespacetoparent() and mangletag() calls. Also: see next
# comment.)
for br in soup.findAll('br'):
  # Thanks to the previous code blocks, the only pure whitespace that can be
  # right before/after a <br> is a newline. Check if previous is not a <br>...
  lf = None
  e = br.previousSibling
  if e != None and e.__class__.__name__ == 'NavigableString' and str(e) == '\n':
    e = e.previousSibling
  if e != None and e.__class__.__name__ == 'Tag' and gettagname(e) != 'br':
    # ...and the next is a <br>...
    nxt = br.nextSibling
    if nxt != None and nxt.__class__.__name__ == 'NavigableString' and str(nxt) == '\n':
      lf = nxt
      nxt = nxt.nextSibling
    if nxt != None and nxt.__class__.__name__ == 'Tag' and gettagname(nxt) == 'br':
      # ...and the one after that is not a <br>...
      e = nxt.nextSibling
      if e != None and e.__class__.__name__ == 'NavigableString' and str(e) == '\n':
        e = e.nextSibling
      if e != None and e.__class__.__name__ == 'Tag' and gettagname(e) != 'br':
        # ...and the parent is a <p>: (Note we only replace if <p> is a direct
        # parent. A double <br> inside an inline tag like <em> is semantically
        # almost the same, but it's too much work to then also close and reopen
        # the inline tags.)
        pe = br.parent
        if gettagname(pe) == 'p':
          # We have exactly two <br>s, inside a <p>.
          # Move contents after t2 to a new paragraph.
          e = nxt.nextSibling
          if e == None:
            # The two br's were at the end of a paragraph. Weirdness.
            # Move them outside (just after) the paragraph.
            pe.parent.insert(getindexinparent(pe) + 1, nxt)
            if lf != None:
              pe.parent.insert(getindexinparent(pe) + 1, lf)
            pe.parent.insert(getindexinparent(pe) + 1, br)
          else:
            # Insert a newline and a new paragraph just after our paragraph.
            # (We always insert one newline, regardless whether the <br>s are
            # followed by newlines.)
            i = getindexinparent(pe) + 1
            p2 = Tag(soup, 'p')
            pe.parent.insert(i, p2)
            e = NavigableString('\n')
            pe.parent.insert(i ,e)
            # Move all content after the second <br> into the new paragraph,
            # after removing a newline if that follows the second <br>.
            e = nxt.nextSibling
            if e != None and e.__class__.__name__ == 'NavigableString' and str(e) == '\n':
              e.extract()
            movecontentsinside(pe, p2, 0, getindexinparent(nxt) + 1)
            # Remove the <br>s and the newline between them (if any)
            nxt.extract()
            br.extract()
            if lf != None:
              lf.extract()

# Remove empty paragraphs after 'block elements'.
if c_remove_empty_paragraphs_under_blocks:
  for tagname in ['table', 'ul']:
    for t in soup.findAll(tagname):
      e2 = t.nextSibling
      while str(e2) == '\n':
        e2 = e2.nextSibling
      if gettagname(e2) == 'p' and len(e2.contents) == 0:
        e2.extract()

# As said above: now that we're done removing spacing, remove <p>s which are
# wrapped insidee (or wrapping?) a single non-positioning tag.
for t in soup.findAll('p'):
  mangletag(t)


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
  # All elements on this level must be 'a' tags.
  for e in elements:
    if saferegexsearch(e, rxglobal_nbspace_only):
      continue
    if gettagname(e) != 'a':
      return False
    href = e.get('href')
    if not href:
      return False
    # Usually there's a link to the index page but not always.
    # The 'nieuw' is a hack for an index page containing buttons, but not to
    # itself.
    if href.endswith('index.htm') or href.endswith('nieuw.htm'):
      # This is not always the first button (that may be a 'previous' link
      # with an arbitrary name) but if we encounter this, we assume these
      # are all button links.
      buttonlink_found = True
  return buttonlink_found

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
    r[i].extract()
    # r is now changed; loop (instead of increasing i).
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
# NB: this is partly effectively stripwhitespacefromend() - but intermixed with empty <p> tags too
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
    # r is now changed; loop (instead of decreasing i).
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

# BeautifulSoup (at least 3.x tested so far) outputs <br />, which is kind-of
# illegal and certainly unnecessary as HTML.
print str(soup).replace('<br />','<br>')
