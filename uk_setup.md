# Instructions for analysing UK Parliament data

We explain how to get hold of speeches made in the UK Parliament and then offer some background history for anyone who likes this sort of thing.

## Getting Speeches

### Requirements

You should create a local directory for the downloaded XML files and note down the path, eg I have a directory 'twf-xml' for everything I pull from TheyWorkForYou and have a subdirectory 'debates' for the XML fies of Hansard.

You should find rsync installed in a lot of Linux installations and on Macs but will need to install it in the Windows Subsystem for Linux (WSL) on a Windows 10/11 machine. 

### Data Download

The easiest source to work with is the data provided by TheyWorkForYou as this is nicely formatted into XML and available for bulk download.

TheyWorkForYou offers [good instructions](https://parser.theyworkforyou.com/hansard.html) on how to download the bulk files, or use the API if you want a smaller set of data.

From the terminal prompt, you can use rsync to pull the XML files for the period you are interested in, for example this would pull data for October 2024 - 
rsync -az --progress --exclude '.svn' --exclude 'tmp/' --relative data.theyworkforyou.com::parldata/scrapedxml/debates/debates2024-10* .

### Data Processing

Once you have a local copy of the XML files, you can run a simple Python script to create separate files for the speeches of each MP found in the dataset.

Run this script from your main working directory (where the XML files are in a subdirectory), eg python uk_member_speeches.py --input-dir twfy-xml/debates --output-dir members.

You can check in your filesystem that there are now XML files for each member and, if happy, move on to the next stage of moving the data into a local database.

The next stage is to build the local database we will use for the analysis using the script uk_build_db.py, eg python uk_build_db.py --input-dir members --output-dir uk

We now have most of our data ready for analysis.  We just need to add in party affiliations for each member in the database.

# The Horrible History of Hansard: From Sneaky Scribblers to Official Scribes!

**The Dastardly Days of Secret Parliament (Before 1771)**

Picture this: Parliament was like the world's most boring secret club! Before 1771, MPs were so secretive they made the Freemasons look like gossips. Publishing what they said was actually *illegal* - you could be fined, imprisoned, or worse! But crafty journalists found sneaky ways around this, disguising parliamentary debates as meetings of made-up societies with ridiculous names like "The Senate of Magna Lilliputia" and "The Lower Room of the Robin Hood Society." [Even politicians' names were disguised](https://en.wikipedia.org/wiki/Hansard) - Sir Robert Walpole became the mysterious "Sr. R―t W―le"!

**Enter the Rebels: Cobbett and the Troublemakers (1803-1812)**

Along came William Cobbett, a radical journalist who thought the public deserved to know what their representatives were up to. In 1803, he started publishing *Parliamentary Debates* - but here's the twist: 
[he didn't actually send reporters to Parliament](https://guides.lib.uchicago.edu/c.php?g=297753&p=1987072)! Instead, he cobbled together reports from newspaper accounts, creating what was essentially parliamentary gossip compiled into books.

**The Hansard Family Takes Over (1812-1889)**

Enter Thomas Curson Hansard, a London printer who'd been helping Cobbett since 1809. When [Cobbett went bankrupt in 1812](https://en.wikipedia.org/wiki/Thomas_Curson_Hansard), Hansard swooped in and bought the whole operation! From 1829, his name appeared on every cover, and "Hansard" became the brand name for parliamentary records - even though [the Hansard family lost control in 1889](https://www.encyclopedia.com/history/encyclopedias-almanacs-transcripts-and-maps/hansard-thomas-curson)!

**From Unofficial Upstarts to Official Records (1909)**

For over a century, Hansard remained a private, unofficial enterprise with [frequent complaints about accuracy](https://hansard.parliament.uk/about?historic=false). Finally, in 
1909, Parliament got fed up and decided to publish its own official version. The irony? They kept calling it "Hansard" even though the Hansard family was long gone!

**The Digital Revolution and the Unofficial Comeback**

Today, you can read every word from [1803 onwards online](https://hansard.parliament.uk/), but here's where it gets interesting again: there's *still* an unofficial version! [TheyWorkForYou.com](https://www.theyworkforyou.com) carries on the tradition of independent parliamentary monitoring, proving that the spirit of those sneaky 18th-century journalists lives on in the digital age.

So there you have it - Hansard started as an illegal act of rebellion, became a family business built on newspaper gossip, turned into an official government publication, and now exists both as stuffy official records AND as a cheeky unofficial website. Some things never change!



