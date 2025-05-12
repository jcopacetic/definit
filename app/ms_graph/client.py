import os 
import msal
import requests
import logging 
import urllib.parse 

from cryptography.fernet import Fernet, InvalidToken

from django.conf import settings

logger = logging.getLogger(__name__)


class MSGraphClient:

    def __init__(self, customer):
        self.ACCESS_TOKEN = self.get_msgraph_access_token(customer)
        self.SITE_ID = customer.msgraph_site_id
        self.DRIVE_ID = customer.msgraph_drive_id

        self.BASE_URL = "https://graph.microsoft.com/v1.0"
        self.SITES_PATH = f"{self.BASE_URL}/sites/{self.SITE_ID}"
        self.DRIVES_PATH = f"{self.BASE_URL}/drives/{self.DRIVE_ID}"
        self.ITEMS_PATH = f"{self.SITES_PATH}/drives/{self.DRIVE_ID}/items"

    def get_msgraph_access_token(self, customer):
        try:
            MSGRAPH_AUTHORITY = f"https://login.microsoftonline.com/{customer.msgraph_tenant_id}"
            app = msal.ConfidentialClientApplication(customer.msgraph_client_id, authority=MSGRAPH_AUTHORITY, client_credential=customer.msgraph_client_secret)
            token_response = app.acquire_token_for_client(scopes=customer.msgraph_scopes)

            if "access_token" in token_response:
                logging.info("Access token obtained successfully.")
                return token_response["access_token"]
            else:
                logging.error("Failed to obtain access token: %s", token_response.get("error_description", "Unknown error"))
                return None
        except Exception as e:
            logging.exception("Error obtaining access token: %s", str(e))
            return None

    def BUILD_HEADERS(self):
        return {"Authorization": f"Bearer {self.ACCESS_TOKEN}"}

    def FILE_NAME_PARSE(self, file_name):
        return urllib.parse.quote(file_name, safe="")

    def LOCAL_PATH(self, download_file_name):
        safe_download_file_name = urllib.parse.quote(download_file_name)

        if not safe_download_file_name.endswith('.xlsx'):
            safe_download_file_name += '.xlsx'

        return os.path.join(os.getcwd(), "downloads", safe_download_file_name)

    def CHECK_DOWNLOAD_FOLDER(self):
        download_folder = os.path.join(os.getcwd(), "downloads")
        if not os.path.exists(download_folder):
            os.makedirs(download_folder)

    def NUMBER_TO_COLUMN(self, n):
        column = ''
        while n > 0:
            n, remainder = divmod(n - 1, 26)
            column = chr(65 + remainder) + column
        return column
    
    def _make_request(self, url, method="GET", params=None, body=None):
        """
        Centralized method to make HTTP requests to the HubSpot API
        
        Args:
            url (str): The URL to make the request to
            method (str, optional): HTTP method (GET, POST, PUT, PATCH, DELETE). Defaults to "GET".
            headers (dict, optional): HTTP headers. Defaults to None.
            params (dict, optional): URL parameters. Defaults to None.
            body (dict, optional): Request body for POST/PUT/PATCH requests. Defaults to None.
            
        Returns:
            dict or None: JSON response if successful, None if error
        """
        try:
            logger.info(f"Making {method} request to: {url}")
            
            if method.upper() == "GET":
                response = requests.get(url, headers=self.BUILD_HEADERS(), params=params)
            elif method.upper() == "POST":
                response = requests.post(url, headers=self.BUILD_HEADERS(), params=params, json=body)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=self.BUILD_HEADERS(), params=params, json=body)
            elif method.upper() == "PATCH":
                response = requests.patch(url, headers=self.BUILD_HEADERS(), params=params, json=body)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=self.BUILD_HEADERS(), params=params)
            else:
                logger.error(f"Unsupported HTTP method: {method}")
                return None
                
            response.raise_for_status()
            
            if response.content:
                return response.json()
            return {}
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error {e.response.status_code}: {e.response.text}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during API request: {e}")
            return None


    def get_sites(self):
        url = f"{self.BASE_URL}/sites"
        sites = self._make_request(url, "GET").get("value", []) 
        return sites

    def get_drives(self):
        url = f"{self.BASE_URL}/sites/{self.SITE_ID}/drives"
        return self._make_request(url, "GET").get("value", [])

    def get_drive_items(self):
        url = f"{self.DRIVES_PATH}/root/children"
        return self._make_request(url, "GET").get("value", [])

    def get_file(self, file_name):
        url = f"{self.DRIVES_PATH}/root:/{self.FILE_NAME_PARSE(file_name)}"
        file_data = self._make_request(url, "GET")
        if "id" in file_data:
            return file_data["id"]
        else:
            return None
        
    def get_file_content(self, file_name):
        url = f"{self.DRIVES_PATH}/root:/{self.FILE_NAME_PARSE(file_name)}:/content"
        return self._make_request(url, "GET")

    def download_spreadsheet(self, file_name, local_path):
        try:
            file_id = self.get_file(file_name)

            if not file_id: 
                logger.error("File ID Not Found!")
                return "File ID Not Found"

            url = f"{self.SITES_PATH}/drive/items/{file_id}/content"

            response = requests.get(url, headers=self.BUILD_HEADERS())
            response.raise_for_status()

            self.CHECK_DOWNLOAD_FOLDER()

            with open(local_path, 'wb') as file:
                file.write(response.content)

            logger.info(f"File downloaded successfully: {local_path}")
            return "Download successful"

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error {e.response.status_code} - {e.response.text}")
            return f"HTTP Error {e.response.status_code}"
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {str(e)}")
            return f"Request error: {str(e)}"
        
    
    def upload_spreadsheet(self, file_path):
        try:
            file_name = os.path.basename(file_path)

            url = f"{self.SITES_PATH}/drives/{self.DRIVE_ID}/root:/{file_name}:/content"

            with open(file_path, 'rb') as file:
                response = requests.put(url, headers=self.BUILD_HEADERS(), data=file)
                response.raise_for_status()

            logger.info(f"File uploaded successfully: {file_name}")
            return "Upload successful"

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error {e.response.status_code} - {e.response.text}")
            return f"HTTP Error {e.response.status_code}"
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {str(e)}")
            return f"Request error: {str(e)}"
        

    def id_row_lookup(
            self,
            id_to_lookup, 
            file_id, 
            worksheet_name, 
            last_row, 
        ):
        try:
            url = f"{self.ITEMS_PATH}/{file_id}/workbook/worksheets('{worksheet_name}')/range(address='A2:A{last_row}')"
            logger.info(f"Constructed URL: {url}")

            response = requests.get(url, headers=self.BUILD_HEADERS())
            response.raise_for_status()

            rows = response.json().get("values", [])

            if not rows:
                logger.info("No rows found in the given range.")
                return False

            for index, row in enumerate(rows):
                if row[0] == int(id_to_lookup):
                    excel_row = index + 2
                    logger.info(f"ID {id_to_lookup} found at Excel row {excel_row}.")
                    return excel_row

            logger.info(f"ID {id_to_lookup} not found in the worksheet.")
            return False

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error {e.response.status_code} - {e.response.text}")
            return f"HTTP Error {e.response.status_code}"
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {str(e)}")
            return f"Request error: {str(e)}"
        


    def edit_spreadsheet_using_api(
            self,
            file_id, 
            worksheet_name,
            data_to_add, 
            row_to_update,
        ):
        
        try:
            amount_parse = (
                f'=HYPERLINK("{data_to_add["quote_link"]}", "{data_to_add["deal_amount"]}")'
                if data_to_add.get("quote_link")
                else data_to_add.get("deal_amount", "")
            )

            
            values = [
                [
                    data_to_add["deal_id"], 
                    f'=HYPERLINK("{data_to_add["deal_link"]}", "{data_to_add["name"]}")', 
                    f'=HYPERLINK("{data_to_add["plans_link"]}", "Link to Plans")',
                    data_to_add["city"],
                    data_to_add["state"],
                    data_to_add["associated_contact"],
                    data_to_add["associated_company"],
                    data_to_add["deal_stage"],
                    data_to_add["deal_owner"],
                    amount_parse,
                    data_to_add["last_contacted"],
                    data_to_add["last_contacted_type"],
                    data_to_add["last_engagement"],
                    data_to_add["last_engagement_type"],
                    data_to_add["email"],
                    data_to_add["call"],
                    data_to_add["meeting"],
                    data_to_add["note"],
                    data_to_add["task"],
                ]
            ]

            target_range = f"A{row_to_update}:S{row_to_update}"

            url = f"{self.ITEMS_PATH}/{file_id}/workbook/worksheets/{worksheet_name}/range(address='{target_range}')"
            body = {
                "values": values
            }

            response = requests.patch(url, headers=self.BUILD_HEADERS(), json=body)
            response.raise_for_status()

            logger.info(f"Data successfully added to row {row_to_update} in {worksheet_name}!")
            return response.json()

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error {e.response.status_code} - {e.response.text}")
            return f"HTTP Error {e.response.status_code}"
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {str(e)}")
            return f"Request error: {str(e)}"
