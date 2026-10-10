import json
import time
import requests

api= "https://api.search.nicovideo.jp/api/v2/snapshot/video/contents/search"
fields_info = "title"+","+"contentId" #"description","tags" can be also added
data = {#"q","targets","_sort","_context" must be written
    "q":"初音ミク","targets":"title","_sort":"-viewCounter","_context":"Mac PC",#for "_context" value, anything is good
    "fields":fields_info,"_offset":3,"_limit":3 #"_offset" and "_limit" values are integer, and can be changed
    }
headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac)"}#for "User-Agent" value, anything is good
def niconico_search():
    for _ in range(1): 
        response = requests.post(api,data=data,headers=headers)
        if response.status_code<300: #"response.status_code.ok" is also good
            print("[API Request is successed]")
            print(response.text)
        else:
            print("[HTTPError]"+str(response.status_code))
        time.sleep(1) # Sleep Time shoud be changed whatever you like
if __name__ == "__main__":
    niconico_search()
    #Reference: https://site.nicovideo.jp/search-api-docs/snapshot
