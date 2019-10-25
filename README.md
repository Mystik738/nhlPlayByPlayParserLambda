# nhlPlayByPlayParserLambda

A simple Lambda function to parse NHL Play by Play files

## Getting started

Deploy Lambda Function in Lambda

Trigger should be S3, ObjectCreated with a suffix of .html. Can optionally add a prefix if you're limiting where these files should be dropped.

## Running

Drop an NHL play by play file into your S3 bucket and wait for it to be turned into a CSV
