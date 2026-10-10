import argparse
import requests
import json

# Initialize about argument
parser = argparse.ArgumentParser()
args = parser.parse_args()
parser.add_argument('-all',action='store_true',help='All the item can be seen')

# Initialize for request
api = "https://qiita.com/api/v2/items"
token = "" #Write your Token getting by Qiita
headers = {"Authorization":"Bearer"+" "+token}
params = {
    "page":"1","per_page":"1","query":"python",
    "tags":[
        {
        "name": "python",
        }
    ]
}

# Execute using Qiita API
def qiita_search():
    response = requests.get(api,params=params,headers=headers)
    if response.status_code<300: #"response.status_code.ok" is also good
        print("[API Request is successed]")
        data = json.loads(response.text)
        for item in data:
            info_print(item["id"],item["title"],item["updated_at"],item["likes_count"],item["stocks_count"])
            if args.all:
                info_print(item)
    else:
        print("[HTTPError]"+str(response.status_code))

def info_print(*args):
    print("-----------------")
    for i in args:
        print(str(i))
    print("-----------------")

if __name__ == "__main__":
    qiita_search()