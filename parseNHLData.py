import json
import boto3
import uuid
import re
from datetime import datetime
from html.parser import HTMLParser
import csv

s3_client = boto3.client('s3')

#This Lambda function is used to convert the NHL's play by play format into a csv file that is later used for database
# entry. An example play by play can be found at http://www.nhl.com/scores/htmlreports/20122013/PL020002.HTM
# The Lambda function itself triggers when an html file is dropped into a particular S3 bucket

#This class is called from the NHLTHMLParser to find player numbers. Each line of the play by play table has a 
# table within it, and that gets parsed here. 
class SubTableParser(HTMLParser):
    
    def __init__(self):
        self.players = []
        self.is_table = False
        HTMLParser.__init__(self)
    
    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.is_table = True
            
    def handle_data(self, data):
        if data.isnumeric():
            self.players.append(data)

#Class that parses the majority of the file to pull out each line of the play by play.        
class NHLHTMLParser(HTMLParser):
    
    #Define a few variables
    def __init__(self):
        #lines is our output, each line should represent an event in the play by play
        self.lines = []
        #A few flags to determine where we are in the parse
        self.in_line = False
        self.in_elem = False
        self.in_header = False
        #The current line we're looking at
        self.line = []
        #A few variables to determine how many relevant tags we're inside
        #tr depth
        self.depth = 0
        #td depth
        self.elem_depth = 0
        #The current element we're looking at
        self.elem = ""
        HTMLParser.__init__(self)
    
    #What to do when we start a tag, typically just flag where we are.
    def handle_starttag(self, tag, attrs):
        if self.in_elem:
            self.elem += "<" + tag + ">"
        if tag == 'td' and self.in_line:
            if not self.in_elem:
                self.in_elem = True
            else:
                self.elem_depth += 1
        if tag == 'tr':
            if self.in_line:
                self.depth += 1
            #The lines we're interested in have this particular attribute, so we flag it
            for attr in attrs:
                if attr[0] == 'class' and (attr[1] == 'evenColor' or attr[1] == 'oddColor'):
                    self.in_line = True
    
    #What to do when we end a tag. If we're flagged to be in the right spot, pull out required data 
    def handle_endtag(self, tag):
        #If we're exiting a top level td element we want to append that element's content to our line
        if self.in_elem and tag == 'td':
            if self.elem_depth == 0:
                self.elem = self.elem.replace('\n', '')
                self.elem = self.elem.replace('\xa0', '')
                self.line.append(self.elem)
                self.elem = ""
                self.in_elem = False
            else:
                 self.elem_depth -= 1
        #This is the bulk of the logic. If we've exited a table row and we're at the top level, pull that
        # information into a line to later put into our csv.                       
        if self.in_line and tag == 'tr':
            if self.depth == 0:
                if self.line[3].find('<br>') != -1:
                    self.line[3] = self.line[3][:self.line[3].find('<')]
                
                #Grab the tables that holds player numbers in it and pull out those numbers
                subParser = SubTableParser()
                subParser.feed(self.line[6])
                if subParser.is_table:
                    self.line[6] = " ".join(subParser.players) 
                subParser.players = []  
                subParser.feed(self.line[7])
                if subParser.is_table:
                    self.line[7] = " ".join(subParser.players)
                    
                #Append this line and reset for the next line    
                self.lines.append(self.line)
                self.line = []
                self.in_line = False
            else:
                self.depth -= 1
        elif self.in_elem:
            self.elem += "</" + tag + ">"

    #Just put all the element data into our variable so we can put it into a line later.
    def handle_data(self, data):
        if self.in_elem:
            self.elem += str(data)

#Main function. Triggers when a file is dropped into S3
def lambda_handler(event, context):
    for record in event['Records']:
        #Get info from event and download the file from S3
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        filepath = key[:key.rfind("/")]
        filename = key[key.rfind("/")+1:]
        download_path = '/tmp/{}'.format(filename)
        
        s3_client.download_file(bucket, key, download_path)
        
        #Some regex that'll allow us to parse the html
        prepattern = re.compile('<pre\b[^>]*>([.\s]*)<\/pre>')
        trpattern = re.compile('<tr class="evenColor">(.*?)<\/tr>')
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
            "Mon.", "Tue.", "Wed.", "Thu.", "Fri.", "Sat.", "Sun." ]
        
        #Open the file
        with open(download_path, 'r') as html_file:
            contents = html_file.read()
            date_line = []
            
            #Find the day the game occurred by checking it against the available days
            for day in weekdays:
                pos = contents.find(day)
                if pos != -1:
                    new = contents[pos:]
                    pos = new.find('<')
                    new = new[:pos]
                    date_line.append([0, 0, 0, 'DATE', 'N/A', '-', datetime.strptime(new, '%A, %B %d, %Y'), '-', '-'])
                    break
             
            #Put the file through the parser to get out the individual lines   
            nhlParser = NHLHTMLParser()
            nhlParser.feed(contents)
        
        #write out our results to a csv file
        with open(download_path[:download_path.find('.')] + '.csv', 'w') as f:
            writer = csv.writer(f, 'unix')
            writer.writerows(date_line)
            writer.writerows(nhlParser.lines)
        
        #Upload the file to S3
        s3_client.upload_file(download_path[:download_path.find('.')] + '.csv', bucket, filepath + "/" + filename[:filename.find('.')] + '.csv')
