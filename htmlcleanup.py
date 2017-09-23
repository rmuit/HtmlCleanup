""" Helper class containing methods that can be used by a HTML cleanup script.

The HtmlCleanupHelper class holds cleanup methods that can be called before
Beautifulsoup comes into play. It's not entirely clear if someone would want to
use this standalone, but we've placed into a separate file so that there are no
unnecessary dependencies.

The best way to start using this is first read a script which uses these
classes.

Some methods throw exceptions for un-parseable HTML; they are not documented
properly yet.
"""

class HtmlCleanupHelper(object):
    """Utility methods for HTML Cleanup."""

    @staticmethod
    def remove_tags(html, tag_name, tag_contents=None):
        """Remove tags from a HTML document. (Don't remove their contents.)

        This method can be used for cleaning unparseable HTML. For instance, MS
        FrontPage output things like <font> <center> </font> </center>, which
        makes HTMLTidy/BeautifulSoup wronlgy 'correct' stuff that would be fine
        if the font tags weren't there, and these misplaced font tags don't add
        anything to the document's formatting.

        tag_contents: a list containing the possible inside contents, i.e.
        attributes (as literal string) of the tags which should be stripped.
        This provides a way of not stripping all tags of this type. (For MSFP
        faulty HTML, if we only strip font tags with the default font face, we
        seem to be left with a legal HTMLdocument.) The code until now assumes
        that there is always a single space between the tag name and the
        contents - unless for '', then it assumes empty contents. If not
        specified, all tags of this type are stripped (including unmatched start
        tags).

        returns: changed html.
        """
        # Set up some values for easier searching, with duplicate-ish values.
        # At least  one of search_simple_tag and search_tag_with_attribute will
        # be true.
        end_tag = '</' +tag_name + '>'
        end_tag_len = len(end_tag)
        simple_start_tag = '<' + tag_name + '>'
        compound_start_tag_start = '<' + tag_name + ' '
        search_compound_tag = False
        start_tags_to_strip = []
        if tag_contents:
            search_simple_tag = False
            for inside in tag_contents:
                if inside:
                    search_compound_tag = True
                    start_tags_to_strip.append(compound_start_tag_start + inside
                                               + '>')
                else:
                    search_simple_tag = True
                    start_tags_to_strip.append(simple_start_tag)
        else:
            # Match simple tag, and any compound tag.
            search_simple_tag = True
            search_compound_tag = True
            start_tags_to_strip.append(simple_start_tag)
            start_tags_to_strip.append(compound_start_tag_start)

        next_process_pos = 0
        found = []
        while True:
            # Find an end tag, then find/store all start tags leading up to it
            # and match the last stored start tag with the end tag. This should
            # accommodate for recursive tags.
            end_pos = html.find(end_tag, next_process_pos)
            start_pos = -2
            while start_pos != -1 and start_pos < end_pos:
                if start_pos != -2:
                    found.append(start_pos)
                    next_process_pos = start_pos + 1
                if search_simple_tag:
                    start_pos = html.find(simple_start_tag, next_process_pos)
                if search_compound_tag:
                    p = html.find(compound_start_tag_start, next_process_pos)
                    if not search_simple_tag or (p != -1 and p < start_pos):
                        start_pos = p
            if end_pos == -1:
                # No more tag pairs / end tags left.
                break
            if not found:
                # Unpaired end tag(s) left. We can't trust that we matched up
                # the right start/end pairs, with the above algorithm. (The
                # position we print is probably wrong because we may have
                # removed tags already; fix that?)
                raise Exception(tag_name + \
                                ' end tag without start tag found at pos ~' +
                                str(end_pos))
            next_process_pos = end_pos + 1

            # Get last non-processed start tag; check if we want to remove it.
            # If not, skip this start/end pair and continue to the next pair.
            start_pos = found.pop()
            for start_tag in start_tags_to_strip:
                if html[start_pos : start_pos + len(start_tag)] == start_tag:
                    # Delete corresponding start/end tags from the html.
                    html = html[:start_pos] + \
                           html[start_pos + len(start_tag) : end_pos] + \
                           html[end_pos + end_tag_len : ]
                    next_process_pos = next_process_pos - len(start_tag) - \
                                       end_tag_len
                    break

        if found and not tag_contents:
            # We have unmatched start tags; we can assume that we matched
            # other start tags up with the right end tags, though. Also, we
            # wanted to remove all tags like this, so just silently remove
            # these start tags.
            while found:
                start_pos = found.pop()
                # Doublecheck. This must always be true.
                if html[start_pos : start_pos + len(simple_start_tag)] \
                   == simple_start_tag:
                    html = html[:start_pos] + \
                           html[start_pos + len(simple_start_tag) : ]
                elif html[start_pos : start_pos
                          + len(compound_start_tag_start)] \
                          == compound_start_tag_start:
                    start_tag_end_pos = html.find('>', start_pos
                                                  + len(compound_start_tag_start))
                    if start_tag_end_pos == -1:
                        # Impossible.
                        raise Exception('No ">" character found for ' + tag_name
                                        + ' tag.')
                    # Check if the '>' is really the end of the start tag, and
                    # not in the middle of some quoted value.
                    start_tag =  html[start_pos :
                                      start_tag_end_pos - start_pos + 1]
                    if start_tag.count('"') % 2 or start_tag.count("'") % 2:
                        # Ain't nobody got time for this.
                        raise Exception('Unsupported ">" character found in '
                                        'quoted attribute value of' + tag_name +
                                        ' tag.')
                    if start_tag.count('<'):
                        # Or this. (Possible that a '>' went missing?)
                        raise Exception('Unsupported "<" character found inside'
                                        + tag_name + ' tag, or no ">" found.')
                    html = html[:start_pos] + \
                           html[start_pos + len(start_tag) : ]

        return html
