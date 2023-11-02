import requests
import argparse
import random
import re
import os
import sys
import threading
import traceback
from tools.autopoisoner.headerfuzz import headersToFuzz

currentPath = os.path.dirname(__file__)

from tools.autopoisoner.print_utils import *


LOCK = threading.Lock()
TIMEOUT_DELAY = 10

outputFile = open("output.txt", "w")

CANARY = "ndvyepenbvtidpvyzh.com"

def splitURLS(threadsSize): #Multithreading

    splitted = []
    URLSsize = len(allURLs)
    width = int(URLSsize/threadsSize)
    if width == 0:
        width = 1
    endVal = 0
    i = 0
    while endVal != URLSsize:
        if URLSsize <= i + 2 * width:
            if len(splitted) == threadsSize - 2:
                endVal = int(i + (URLSsize - i)/2)
            else:
                endVal = URLSsize
        else:
            endVal = i + width

        splitted.append(allURLs[i: endVal])
        i += width

    return splitted

def canary_in_response(response : requests.Response):
    for val in response.headers.values():
        if CANARY in val:
            return True
    if CANARY in response.text:
        return True

    return False

def crawl_files(URL, response : requests.Response):
    responseText = response.text
    regexp1 = '(?<=src=")(\/[^\/].+?)(?=")'
    regexp2 = '(?<=href=")(\/[^\/].+?)(?=")'

    filesURL = re.findall(regexp1, responseText)
    filesURL += re.findall(regexp2, responseText)

    selectedFiles = []

    #Select two random extensions

    if len(filesURL) >= 2:
        selectedFiles = random.sample(filesURL,2)
    elif len(filesURL) == 1:
        selectedFiles = [filesURL[0]]

    for i in range(len(selectedFiles)):
        selectedFiles[i] = URL + selectedFiles[i]

    return selectedFiles

def use_caching(headers):
    if  headers.get("X-Cache-Hits") or headers.get("X-Vercel-Cache") or headers.get("x-vercel-cache") or headers.get("X-Cache") or headers.get("x-drupal-cache") \
    or headers.get("X-HS-CF-Cache-Status") or headers.get("Age") or headers.get("x-vanilla-cache-control") or headers.get("Cf-Cache-Status") \
    or headers.get("X-Proxy-Cache") or headers.get("X-TZLA-EDGE-Cache-Hit") or headers.get("X-nananana") or headers.get("x-spip-cache") \
    or headers.get("x-pangle-cache-from") or headers.get("X-Deploy-Web-Server-Cache-Hit") or headers.get("X-Micro-Cache") or headers.get("X-Deploy-Web-Server-Cache-Hit") \
    or (headers.get("Cache-Control") and ("public" in headers.get("Cache-Control"))):
        return True
    else:
        return False

def vulnerability_confirmed(responseCandidate : requests.Response, url, randNum, buster, custom_header):
    try:
        confirmationResponse = requests.get(f"{url}?cacheBusterX{randNum}={buster}", allow_redirects=False, verify=False, timeout=TIMEOUT_DELAY, headers=custom_header)
    except:
        #traceback.print_exc()
        return False
    if confirmationResponse.status_code == responseCandidate.status_code and confirmationResponse.text == responseCandidate.text:
        if canary_in_response(responseCandidate):
            if canary_in_response(confirmationResponse):
                return True
            else:
                return False
        else:
            return True
    else:
        return False

def base_request(url, custom_header):
    randNum = str(random.randrange(999))
    buster = str(random.randrange(999))
    try:
        response = requests.get(f"{url}?cacheBusterX{randNum}={buster}", verify=False, allow_redirects=False, timeout=TIMEOUT_DELAY, headers=custom_header)
        return response
    except:
        #traceback.print_exc()
        return None


def port_poisoning_check(url, initialResponse, custom_header):
    randNum = str(random.randrange(999))
    buster = str(random.randrange(999))
    findingState = 0

    host = url.split("://")[1].split("/")[0]
    response = None
    custom_head = {
            "Host": f"{host}:8888",
            }
    if custom_header:
        custom_head = custom_head.update(custom_header)
    try:
        response = requests.get(f"{url}?cacheBusterX{randNum}={buster}", headers=custom_head, verify=False, allow_redirects=False, timeout=TIMEOUT_DELAY)
        uri = f"{url}?cacheBusterX{randNum}={buster}"
    except:
        #traceback.print_exc()
        return None
    explicitCache = str(use_caching(response.headers)).upper()

    if response.status_code != initialResponse.status_code:
        findingState = 1
        potential_verbose_message("STATUS_CODE", url)
        if vulnerability_confirmed(response, url, randNum, buster, custom_header):
            findingState = 2
            behavior_or_confirmed_message(uri, "CONFIRMED", "STATUS", explicitCache, url, header=custom_head, outputFile=outputFile,LOCK = LOCK)
        else:
            potential_verbose_message("UNSUCCESSFUL", url)
            if behavior:
                behavior_or_confirmed_message(uri, "BEHAVIOR", "STATUS", explicitCache, url, header=custom_head)

    elif abs(len(response.text) - len(initialResponse.text)) > 0.25 * len(initialResponse.text):
        findingState = 1
        potential_verbose_message("LENGTH", url)
        if vulnerability_confirmed(response, url, randNum, buster, custom_header):
            findingState = 2
            behavior_or_confirmed_message(uri, "CONFIRMED", "LENGTH", explicitCache, url, header=custom_head, outputFile=outputFile, LOCK = LOCK)

        else:
            potential_verbose_message("UNSUCCESSFUL",  url)
            if behavior:
                behavior_or_confirmed_message(uri, "BEHAVIOR", "LENGTH", explicitCache, url, header=custom_head)

    if findingState == 1:
        return "UNCONFIRMED"

def headers_poisoning_check(url, initialResponse, custom_header):
    findingState = 0
    for header in headersToFuzz.keys():
        payload = {header: headersToFuzz[header]}
        randNum = str(random.randrange(999))
        buster = str(random.randrange(999))
        uri = f"{url}?cacheBusterX{randNum}={buster}"
        response = None
        try:
            response = requests.get(uri, headers=payload, verify=False, allow_redirects=False, timeout=TIMEOUT_DELAY)
        except KeyboardInterrupt:
            pass
        except:
            potential_verbose_message("ERROR", url)
            print("Request error, Skipping the {} URL with {}".format(uri, payload))
            #traceback.print_exc()
            continue
        explicitCache = str(use_caching(response.headers)).upper()
        sys.stdout.write("\033[34m  {}\033[0m\r".format(header))
        sys.stdout.write("\033[K")

        if canary_in_response(response):
            findingState = 1
            potential_verbose_message("CANARY", url)
            if vulnerability_confirmed(response, url, randNum, buster, custom_header):
                findingState = 2
                behavior_or_confirmed_message(uri, "CONFIRMED", "REFLECTION", explicitCache, url, header=payload, outputFile=outputFile, LOCK = LOCK)

            else:
                potential_verbose_message("UNSUCCESSFUL", url)
                if behavior:
                    behavior_or_confirmed_message(uri, "BEHAVIOR", "REFLECTION", explicitCache, url, header=payload)

        elif response.status_code != initialResponse.status_code:
            findingState = 1
            potential_verbose_message("STATUS_CODE", url)
            if vulnerability_confirmed(response, url, randNum, buster, custom_header):
                findingState = 2
                behavior_or_confirmed_message(uri, "CONFIRMED", "STATUS", explicitCache, url, header=payload, outputFile=outputFile,LOCK = LOCK)
            else:
                potential_verbose_message("UNSUCCESSFUL", url)
                if behavior:
                    behavior_or_confirmed_message(uri, "BEHAVIOR", "STATUS", explicitCache, url, header=payload)

        elif abs(len(response.text) - len(initialResponse.text)) > 0.25 * len(initialResponse.text):
            findingState = 1
            potential_verbose_message("LENGTH", url)
            if vulnerability_confirmed(response, url, randNum, buster, custom_header):
                findingState = 2
                behavior_or_confirmed_message(uri, "CONFIRMED", "LENGTH", explicitCache, url, header=payload, outputFile=outputFile, LOCK = LOCK)
            else:
                potential_verbose_message("UNSUCCESSFUL", url)
                if behavior:
                    behavior_or_confirmed_message(uri, "BEHAVIOR", "LENGTH", explicitCache, url, header=payload)

    if findingState == 1:
        return "UNCONFIRMED"

def crawl_and_scan(url, initialResponse, custom_header):
    selectedURLS = crawl_files(url, initialResponse)
    for url in selectedURLS:
        potential_verbose_message("CRAWLING", url)
        initResponse = base_request(url, custom_header)
        port_poisoning_check(url, initResponse, custom_header)
        headers_poisoning_check(url, initResponse, custom_header)


def cache_poisoning_check(url, custom_header):
    initialResponse = base_request(url, custom_header)

    if initialResponse.status_code in (200, 304, 302, 301, 401, 402, 403, 303, 404, 400, 500):
        resultPort = port_poisoning_check(url, initialResponse, custom_header)
        resultHeaders = headers_poisoning_check(url, initialResponse, custom_header)
        if resultHeaders == "UNCONFIRMED" or resultPort == "UNCONFIRMED":
            crawl_and_scan(url, initialResponse, custom_header)

    if not initialResponse:
        #traceback.print_exc()
        potential_verbose_message("ERROR", url)
        return

def sequential_cache_poisoning_check(urlList):

    for url in urlList:
        cache_poisoning_check(url)

def check_cache_poisoning(url, custom_header, behavior_):
    print("\033[36m ├ Cache poisoning analyse\033[0m")

    global behavior
    behavior = behavior_

    if url:
        try:
            cache_poisoning_check(url, custom_header)
        except:
            print("\nInvalid URL")
            traceback.print_exc()
    elif file:
        if not args.threads or args.threads == 1:
            sequential_cache_poisoning_check(allURLs)
        else:
            workingThreads = []
            split = splitURLS(args.threads)
            for subList in split:
                t = threading.Thread(target=sequential_cache_poisoning_check, args=[subList])
                workingThreads.append(t)
            for thread in workingThreads:
                thread.start()
            for thread in workingThreads:
                thread.join()
    outputFile.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument("--file", "-f", type=str, required=False, help="file containing URLs to be tested")
    parser.add_argument("--url", "-u", type=str, required=False, help="url to be tested")
    parser.add_argument("--threads", "-n", type=int, required=False, help= 'number of threads for the tool')
    parser.add_argument("--output", "-o", type=str, required=False, help='output file path')
    parser.add_argument("--verbose", "-v", required=False, action='store_true', help="activate verbose mode")
    parser.add_argument("--behavior", "-b", required=False, action='store_true', help="activate a lighter version of verbose, highlighting interesting cache behavior") 

    args = parser.parse_args()
    if not (args.file or args.url):
        parser.error('No input selected: Please add --file or --url.')

    if args.output:
        outputFile = open(args.output, "w")
    else:
        outputFile = open("output.txt", "w")

    if args.file :
        try:
            allURLs = [line.replace('\n', '') for line in open(args.file, "r")]
        except FileNotFoundError:
            print("Error, input file not found")
            sys.exit()
    check_cache_poisoning(args.url)
