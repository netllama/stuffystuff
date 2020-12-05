#!/bin/python
# update jigl generated info pages with a google maps iframe which 
# corresponds to the GPS coordinates in the image EXIF data
# expects the name of an jigl generated *_info.html file to update as a parameter

from __future__ import division
import os
import sys
import re
import fileinput

if len(sys.argv) != 2:
	print('\nMissing filename argument')
	sys.exit(1)

filename = str(sys.argv[1])
print(f'\nProcessing {filename}')
NS_regex = '^(<nobr>&nbsp;:&nbsp;){1}[SN]{1}\s+\d{1,3}d\s+\d{1,2}m\s+\d{1,2}\.\d{1,4}(s<br>)$'
EW_regex = '^(<nobr>&nbsp;:&nbsp;){1}[EW]{1}\s+\d{1,3}d\s+\d{1,2}m\s+\d{1,2}\.\d{1,4}(s<br>)$'
comment_html = '<nobr>Comment<br>\n'
map_html = '<nobr>Map&nbsp;:&nbsp;<br>\n'
nobr_data_br_regex = '^(<nobr>){1}[A-Za-z\/\.\s]+(<br>){1}$'
nobr_data_br_counter = 1
nobr_2space_regex = '^(<nobr>&nbsp;:&nbsp;){1}.+$'
nobr_2space = '<nobr>&nbsp;:&nbsp;'
nobr_2space_counter = 0
rewriteFileNS = False
rewriteFileEW = False

def getCoords(coords):
    negative = ''
    direction = coords.split(';')[-1].split()[0]
    if direction == 'S' or direction == 'W':
    	negative = '-'
    deg = float(coords.split(';')[-1].split()[1].replace('d',''))
    minute = float(coords.split(';')[-1].split()[2].replace('m','')) / 60
    second = float(coords.split(';')[-1].split()[3].replace('s<br>','')) / 3600
    newCoords = str(deg + minute + second)
    return f'{negative}{newCoords}'

for line in fileinput.input([filename], openhook=fileinput.hook_encoded("utf-8")):
    match_nobr_data = re.match(nobr_data_br_regex, line)
    if match_nobr_data:
    	nobr_data_br_counter += 1
    matchObj = re.match(NS_regex, line)
    if matchObj:
        rewriteFileNS = True
        NS = matchObj.group()
        NS_coords = getCoords(NS)
    matchObj = re.match(EW_regex, line)
    if matchObj:
        rewriteFileEW = True
        EW = matchObj.group()
        EW_coords = getCoords(EW)

# add vertical spacers for field name column
spacer = '<nobr><br>\n' * ( nobr_data_br_counter + ( 22 - nobr_data_br_counter ))
if rewriteFileNS and rewriteFileEW:
    mapHTML = '''
<nobr><iframe width="425" height="350" frameborder="0" scrolling="no" marginheight="0" marginwidth="0" 
src="https://maps.google.com/maps?f=q&amp;source=s_q&amp;hl=en&amp;geocode=&amp;q={},{}&amp;aq=&amp;sll=37.6,-95.665&amp;sspn=48.408958,76.201172&amp;ie=UTF8&amp;t=m&amp;z=11&amp;ll={},{}&amp;output=embed">
</iframe><br>
'''.format(NS_coords, EW_coords, NS_coords, EW_coords)
    for line in fileinput.input([filename], inplace=True):
        if line == comment_html:
            sys.stdout.write (line + map_html + spacer)
        else:
            sys.stdout.write (line)
        if re.match(nobr_2space_regex, line):
            nobr_2space_counter += 1
            if (nobr_2space_counter + 1) == nobr_data_br_counter:
                sys.stdout.write (mapHTML)
