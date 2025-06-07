# Instructions for analysing UK Parliament data

## Some History


## Getting Speeches

The easiest source to work with is the data provided by TheyWorkForYou as this is nicely formatted into XML and available for bulk download.

TheyWorkForYou offers (good instructions)[https://parser.theyworkforyou.com/hansard.html] on how to download the bulk files, or use the API if you want a smaller set of data.

You can use rsync to pull the XML files for the period you are interested in, for example this would pull data for the year 2024 - 
rsync -az --progress --exclude '.svn' --exclude 'tmp/' --relative data.theyworkforyou.com::parldata/scrapedxml/debates/debates2024-* .

