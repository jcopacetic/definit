
            
import os
import logging
import requests
import msal
import urllib.parse
from typing import Dict, List, Union, Optional, Any, Tuple

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('graph_workbook_client.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class MSGraphClient:
    def __init__(self, customer: object):
        """
        Initialize the Microsoft Graph Workbook Client
        
        Args:
            access_token (str): The Microsoft Graph API access token
            site_id (str, optional): The SharePoint site ID
            drive_id (str, optional): The drive ID
        """
        self.access_token = self.get_msgraph_access_token(customer)
        self.site_id = customer.msgraph_site_id
        self.drive_id = customer.msgraph_drive_id
        self.base_url = "https://graph.microsoft.com/v1.0"
        
        self.sites_path = f"{self.base_url}/sites/{self.site_id}"
        self.drives_path = f"{self.base_url}/drives/{self.drive_id}"
        self.items_path = f"{self.sites_path}/drives/{self.drive_id}/items"
        
        # Create download folder if it doesn't exist
        self._check_download_folder()
    
    def get_msgraph_access_token(self, customer):
        try:
            MSGRAPH_AUTHORITY = f"https://login.microsoftonline.com/{customer.msgraph_tenant_id}"
            app = msal.ConfidentialClientApplication(customer.msgraph_client_id, authority=MSGRAPH_AUTHORITY, client_credential=customer.msgraph_client_secret)
            token_response = app.acquire_token_for_client(scopes=[customer.msgraph_scopes,])

            if "access_token" in token_response:
                logging.info("Access token obtained successfully.")
                return token_response["access_token"]
            else:
                logging.error("Failed to obtain access token: %s", token_response.get("error_description", "Unknown error"))
                return None
        except Exception as e:
            logging.exception("Error obtaining access token: %s", str(e))
            return None
    
    def _headers(self) -> Dict[str, str]:
        """Build the headers for API requests"""
        return {"Authorization": f"Bearer {self.access_token}"}
    
    def _safe_file_name(self, file_name: str) -> str:
        """URL encode a file name safely"""
        return urllib.parse.quote(file_name, safe="")
    
    def _local_path(self, download_file_name: str) -> str:
        """Generate a safe local file path"""
        safe_download_file_name = urllib.parse.quote(download_file_name)

        if not safe_download_file_name.endswith('.xlsx'):
            safe_download_file_name += '.xlsx'

        return os.path.join(os.getcwd(), "downloads", safe_download_file_name)
    
    def _check_download_folder(self) -> None:
        """Ensure download folder exists"""
        download_folder = os.path.join(os.getcwd(), "downloads")
        if not os.path.exists(download_folder):
            os.makedirs(download_folder)
    
    def _column_letter(self, n: int) -> str:
        """Convert a column number to Excel column letter (A, B, C, ..., Z, AA, AB, ...)"""
        column = ''
        while n > 0:
            n, remainder = divmod(n - 1, 26)
            column = chr(65 + remainder) + column
        return column
    
    def _make_request(self, method: str, url: str, headers: Dict = None, json_data: Dict = None, 
                     data: Any = None, params: Dict = None) -> Dict:
        """Make an HTTP request and handle errors"""
        if headers is None:
            headers = self._headers()
        
        try:
            response = requests.request(
                method=method, 
                url=url, 
                headers=headers, 
                json=json_data,
                data=data,
                params=params
            )
            response.raise_for_status()
            
            if response.content:
                try:
                    return response.json()
                except ValueError:
                    return {"content": response.content}
            return {}
            
        except requests.exceptions.HTTPError as e:
            logger.error(
                "HTTP Error %s - %s",
                getattr(e.response, "status_code", "Unknown"),
                getattr(e.response, "text", "No response text")
            )
            raise
        
        except requests.exceptions.RequestException as e:
            logger.exception(f"Request error: {str(e)}")
            raise
    
    def get_sites(self) -> List[Dict]:
        """
        Get all available SharePoint sites.
        
        Returns:
            List[Dict]: List of site objects
        """
        url = f"{self.base_url}/sites"
        
        result = self._make_request("GET", url)
        sites = result.get("value", [])
        
        if sites:
            logger.info(f"Retrieved {len(sites)} sites.")
        else:
            logger.warning("No Sites Found.")
            
        return sites
    
    def get_site_by_name(self, site_name: str) -> Optional[Dict]:
        """
        Find a site by name
        
        Args:
            site_name (str): The name of the site to find
            
        Returns:
            Optional[Dict]: The site object if found, None otherwise
        """
        sites = self.get_sites()
        for site in sites:
            if site.get("displayName") == site_name or site.get("name") == site_name:
                logger.info(f"Found site: {site_name}")
                self.site_id = site.get("id")
                return site
        
        logger.warning(f"Site '{site_name}' not found.")
        return None
        
    def get_site_by_path(self, hostname: str, site_path: str) -> Dict:
        """
        Get a site by hostname and path
        
        Args:
            hostname (str): The hostname (e.g. 'contoso.sharepoint.com')
            site_path (str): The site path (e.g. '/sites/marketing')
        
        Returns:
            Dict: The site object
        """
        url = f"{self.base_url}/sites/{hostname}:{site_path}"
        result = self._make_request("GET", url)
        
        if result and "id" in result:
            logger.info(f"Found site at path {site_path}")
            self.site_id = result.get("id")
        
        return result
    
    def get_drives(self, site_id: str = None) -> List[Dict]:
        """
        Get all available drives in a site.
        
        Args:
            site_id (str, optional): The site ID. Uses instance site_id if not provided.
            
        Returns:
            List[Dict]: List of drive objects
        """
        if not site_id and not self.site_id:
            logger.error("Site ID is required")
            return []
        
        site_id_to_use = site_id or self.site_id
        url = f"{self.base_url}/sites/{site_id_to_use}/drives"
        
        result = self._make_request("GET", url)
        drives = result.get("value", [])
        
        if drives:
            logger.info(f"Retrieved {len(drives)} drives.")
        else:
            logger.warning("No Drives Found.")
            
        return drives
    
    def get_drive_by_name(self, drive_name: str, site_id: str = None) -> Optional[Dict]:
        """
        Find a drive by name
        
        Args:
            drive_name (str): The name of the drive to find
            site_id (str, optional): The site ID. Uses instance site_id if not provided.
            
        Returns:
            Optional[Dict]: The drive object if found, None otherwise
        """
        drives = self.get_drives(site_id)
        for drive in drives:
            if drive.get("name") == drive_name:
                logger.info(f"Found drive: {drive_name}")
                self.drive_id = drive.get("id")
                return drive
                
        logger.warning(f"Drive '{drive_name}' not found.")
        return None
    
    def get_drive_items(self, drive_id: str = None) -> List[Dict]:
        """
        Get all items in a drive.
        
        Args:
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            List[Dict]: List of drive item objects
        """
        if not drive_id and not self.drive_id:
            logger.error("Drive ID is required")
            return []
            
        drive_id_to_use = drive_id or self.drive_id
        url = f"{self.base_url}/drives/{drive_id_to_use}/root/children"
        
        result = self._make_request("GET", url)
        drive_items = result.get("value", [])
        
        if drive_items:
            logger.info(f"Retrieved {len(drive_items)} items from the drive.")
        else:
            logger.warning("No items found in the drive.")
            
        return drive_items
    
    def get_folder_items(self, folder_path: str, drive_id: str = None) -> List[Dict]:
        """
        Get items in a specific folder.
        
        Args:
            folder_path (str): Path to the folder
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            List[Dict]: List of folder item objects
        """
        if not drive_id and not self.drive_id:
            logger.error("Drive ID is required")
            return []
            
        drive_id_to_use = drive_id or self.drive_id
        safe_path = self._safe_file_name(folder_path)
        url = f"{self.base_url}/drives/{drive_id_to_use}/root:/{safe_path}:/children"
        
        result = self._make_request("GET", url)
        folder_items = result.get("value", [])
        
        if folder_items:
            logger.info(f"Retrieved {len(folder_items)} items from folder '{folder_path}'.")
        else:
            logger.warning(f"No items found in folder '{folder_path}'.")
            
        return folder_items
    
    def search_items(self, search_term: str, drive_id: str = None) -> List[Dict]:
        """
        Search for items in the drive.
        
        Args:
            search_term (str): The search query
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            List[Dict]: List of matching items
        """
        if not drive_id and not self.drive_id:
            logger.error("Drive ID is required")
            return []
            
        drive_id_to_use = drive_id or self.drive_id
        url = f"{self.base_url}/drives/{drive_id_to_use}/root/search(q='{search_term}')"
        
        result = self._make_request("GET", url)
        search_results = result.get("value", [])
        
        if search_results:
            logger.info(f"Found {len(search_results)} items matching '{search_term}'.")
        else:
            logger.warning(f"No items found matching '{search_term}'.")
            
        return search_results
    
    def get_item(self, item_path: str, drive_id: str = None) -> Optional[Dict]:
        """
        Get a specific item by path.
        
        Args:
            item_path (str): Path to the item
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            Optional[Dict]: The item object if found, None otherwise
        """
        if not drive_id and not self.drive_id:
            logger.error("Drive ID is required")
            return None
            
        drive_id_to_use = drive_id or self.drive_id
        safe_path = self._safe_file_name(item_path)
        url = f"{self.base_url}/drives/{drive_id_to_use}/root:/{safe_path}"
        
        try:
            result = self._make_request("GET", url)
            
            if "id" in result:
                logger.info(f"Item '{item_path}' found with ID: {result['id']}")
                return result
            else:
                logger.warning(f"Item '{item_path}' not found.")
                return None
                
        except requests.exceptions.HTTPError:
            logger.warning(f"Item '{item_path}' not found.")
            return None
    
    def get_item_by_id(self, item_id: str, drive_id: str = None) -> Dict:
        """
        Get a specific item by ID.
        
        Args:
            item_id (str): ID of the item
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            Dict: The item object
        """
        if not drive_id and not self.drive_id:
            logger.error("Drive ID is required")
            return {}
            
        drive_id_to_use = drive_id or self.drive_id
        url = f"{self.base_url}/drives/{drive_id_to_use}/items/{item_id}"
        
        result = self._make_request("GET", url)
        
        if "id" in result:
            logger.info(f"Item with ID '{item_id}' found.")
        else:
            logger.warning(f"Item with ID '{item_id}' not found.")
            
        return result
    
    def get_workbooks(self, folder_path: str = "", drive_id: str = None) -> List[Dict]:
        """
        Get all Excel workbooks in a drive or folder.
        
        Args:
            folder_path (str, optional): Path to the folder. Default is root.
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            List[Dict]: List of workbook objects
        """
        if folder_path:
            items = self.get_folder_items(folder_path, drive_id)
        else:
            items = self.get_drive_items(drive_id)
        
        workbooks = []
        for item in items:
            name = item.get("name", "")
            if name.endswith((".xlsx", ".xlsm", ".xlsb", ".xls")):
                workbooks.append(item)
        
        if workbooks:
            logger.info(f"Found {len(workbooks)} workbooks.")
        else:
            logger.warning("No workbooks found.")
            
        return workbooks
    
    def get_workbook_by_name(self, workbook_name: str, folder_path: str = "", drive_id: str = None) -> Optional[Dict]:
        """
        Find a workbook by name.
        
        Args:
            workbook_name (str): The name of the workbook to find
            folder_path (str, optional): Path to the folder. Default is root.
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            Optional[Dict]: The workbook object if found, None otherwise
        """
        # Add .xlsx extension if not already present
        if not any(workbook_name.endswith(ext) for ext in [".xlsx", ".xlsm", ".xlsb", ".xls"]):
            workbook_name += ".xlsx"
        
        if folder_path:
            search_path = f"{folder_path}/{workbook_name}"
        else:
            search_path = workbook_name
            
        return self.get_item(search_path, drive_id)
    
    def get_worksheets(self, workbook_item_id: str, drive_id: str = None) -> List[Dict]:
        """
        Get all worksheets in a workbook.
        
        Args:
            workbook_item_id (str): The ID of the workbook item
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            List[Dict]: List of worksheet objects
        """
        if not drive_id and not self.drive_id:
            logger.error("Drive ID is required")
            return []
            
        drive_id_to_use = drive_id or self.drive_id
        url = f"{self.base_url}/drives/{drive_id_to_use}/items/{workbook_item_id}/workbook/worksheets"
        
        result = self._make_request("GET", url)
        worksheets = result.get("value", [])
        
        if worksheets:
            logger.info(f"Retrieved {len(worksheets)} worksheets.")
        else:
            logger.warning("No worksheets found.")
            
        return worksheets
    
    def get_worksheet_by_name(self, workbook_item_id: str, worksheet_name: str, drive_id: str = None) -> Optional[Dict]:
        """
        Find a worksheet by name.
        
        Args:
            workbook_item_id (str): The ID of the workbook item
            worksheet_name (str): The name of the worksheet to find
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            Optional[Dict]: The worksheet object if found, None otherwise
        """
        worksheets = self.get_worksheets(workbook_item_id, drive_id)
        
        for worksheet in worksheets:
            if worksheet.get("name") == worksheet_name:
                logger.info(f"Found worksheet: {worksheet_name}")
                return worksheet
                
        logger.warning(f"Worksheet '{worksheet_name}' not found.")
        return None
    
    def get_worksheet_by_index(self, workbook_item_id: str, index: int, drive_id: str = None) -> Optional[Dict]:
        """
        Get a worksheet by position index (0-based).
        
        Args:
            workbook_item_id (str): The ID of the workbook item
            index (int): The 0-based index of the worksheet
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            Optional[Dict]: The worksheet object if found, None otherwise
        """
        worksheets = self.get_worksheets(workbook_item_id, drive_id)
        
        if 0 <= index < len(worksheets):
            logger.info(f"Found worksheet at index {index}: {worksheets[index].get('name')}")
            return worksheets[index]
        else:
            logger.warning(f"Worksheet at index {index} not found.")
            return None
    
    def get_range(self, workbook_item_id: str, worksheet_id: str, range_address: str, drive_id: str = None) -> Dict:
        """
        Get a range of cells from a worksheet.
        
        Args:
            workbook_item_id (str): The ID of the workbook item
            worksheet_id (str): The ID or name of the worksheet
            range_address (str): The Excel range address (e.g. 'A1:B10')
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            Dict: The range object with values
        """
        if not drive_id and not self.drive_id:
            logger.error("Drive ID is required")
            return {}
            
        drive_id_to_use = drive_id or self.drive_id
        url = f"{self.base_url}/drives/{drive_id_to_use}/items/{workbook_item_id}/workbook/worksheets/{worksheet_id}/range(address='{range_address}')"
        
        result = self._make_request("GET", url)
        
        if "values" in result:
            logger.info(f"Retrieved range {range_address}")
        else:
            logger.warning(f"Failed to retrieve range {range_address}")
            
        return result
    
    def get_used_range(self, workbook_item_id: str, worksheet_id: str, drive_id: str = None) -> Dict:
        """
        Get the used range of a worksheet.
        
        Args:
            workbook_item_id (str): The ID of the workbook item
            worksheet_id (str): The ID or name of the worksheet
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            Dict: The used range object with values
        """
        if not drive_id and not self.drive_id:
            logger.error("Drive ID is required")
            return {}
            
        drive_id_to_use = drive_id or self.drive_id
        url = f"{self.base_url}/drives/{drive_id_to_use}/items/{workbook_item_id}/workbook/worksheets/{worksheet_id}/usedRange"
        
        result = self._make_request("GET", url)
        
        if "values" in result:
            num_rows = len(result.get("values", [])) + 2
            logger.info(f"Retrieved used range with {num_rows} rows")
        else:
            logger.warning("Failed to retrieve used range")
            
        return result
    
    def get_worksheet_headers(self, workbook_item_id: str, worksheet_id: str, header_row: int = 1, drive_id: str = None) -> List[str]:
        """
        Get the column headers from a worksheet.
        
        Args:
            workbook_item_id (str): The ID of the workbook item
            worksheet_id (str): The ID or name of the worksheet
            header_row (int, optional): The row containing headers (1-based). Default is 1.
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            List[str]: The header values
        """
        # First get used range to determine the width
        used_range = self.get_used_range(workbook_item_id, worksheet_id, drive_id)
        
        if not used_range or "values" not in used_range:
            logger.warning("Could not retrieve used range")
            return []
            
        # If no data in worksheet
        if not used_range.get("values"):
            logger.warning("Worksheet appears to be empty")
            return []
            
        header_row_index = header_row - 1  # Convert to 0-based
        
        # If requested header row is not within the data
        if header_row_index >= len(used_range["values"]):
            logger.warning(f"Header row {header_row} is beyond the data range")
            return []
            
        # Get just the header row
        header_values = used_range["values"][header_row_index]
        
        # Filter out None or empty values at the end
        while header_values and (header_values[-1] is None or header_values[-1] == ""):
            header_values.pop()
            
        logger.info(f"Retrieved {len(header_values)} headers from row {header_row}")
        return header_values
    
    def get_column_index_by_header(self, workbook_item_id: str, worksheet_id: str, 
                                header_name: str, header_row: int = 1, drive_id: str = None) -> Optional[int]:
        """
        Find a column index by its header name.
        
        Args:
            workbook_item_id (str): The ID of the workbook item
            worksheet_id (str): The ID or name of the worksheet
            header_name (str): The header name to find
            header_row (int, optional): The row containing headers (1-based). Default is 1.
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            Optional[int]: The 1-based column index if found, None otherwise
        """
        headers = self.get_worksheet_headers(workbook_item_id, worksheet_id, header_row, drive_id)
        
        for i, header in enumerate(headers):
            if header == header_name:
                logger.info(f"Found header '{header_name}' at column index {i+1}")
                return i + 1
                
        logger.warning(f"Header '{header_name}' not found")
        return None
    
    def get_column_letter_by_header(self, workbook_item_id: str, worksheet_id: str, 
                                  header_name: str, header_row: int = 1, drive_id: str = None) -> Optional[str]:
        """
        Find a column letter by its header name.
        
        Args:
            workbook_item_id (str): The ID of the workbook item
            worksheet_id (str): The ID or name of the worksheet
            header_name (str): The header name to find
            header_row (int, optional): The row containing headers (1-based). Default is 1.
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            Optional[str]: The column letter if found, None otherwise
        """
        column_index = self.get_column_index_by_header(workbook_item_id, worksheet_id, header_name, header_row, drive_id)
        
        if column_index:
            column_letter = self._column_letter(column_index)
            logger.info(f"Column letter for '{header_name}' is {column_letter}")
            return column_letter
            
        return None
    
    def find_row_by_value(self, workbook_item_id: str, worksheet_id: str, column: str, 
                        search_value: Any, case_sensitive: bool = False, drive_id: str = None) -> Optional[int]:
        """
        Find a row by a value in a specific column.
        
        Args:
            workbook_item_id (str): The ID of the workbook item
            worksheet_id (str): The ID or name of the worksheet
            column (str): The column letter or header name
            search_value (Any): The value to search for
            case_sensitive (bool, optional): Whether the search is case sensitive. Default is False.
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            Optional[int]: The 1-based row index if found, None otherwise
        """
        # If column is a header name, get column letter
        if len(column) > 1 and not column.isalpha():
            column_letter = self.get_column_letter_by_header(workbook_item_id, worksheet_id, column, drive_id=drive_id)
            if not column_letter:
                logger.warning(f"Column header '{column}' not found")
                return None
            column = column_letter
        
        # Get used range to determine data boundaries
        used_range = self.get_used_range(workbook_item_id, worksheet_id, drive_id)
        
        if not used_range or "values" not in used_range or not used_range["values"]:
            logger.warning("No data found in worksheet")
            return None
            
        # Parse address to get starting row and max row
        address = used_range.get("address", "")
        if not address:
            logger.warning("Could not determine used range address")
            return None
            
        # Address format is typically like "Sheet1!A1:G100"
        # We need to extract the row range
        parts = address.split("!")
        if len(parts) < 2:
            logger.warning(f"Unexpected address format: {address}")
            return None
            
        cell_range = parts[1]
        range_parts = cell_range.split(":")
        if len(range_parts) < 2:
            logger.warning(f"Unexpected range format: {cell_range}")
            return None
            
        # Extract the start row (skip sheet name and column letters)
        start_row_str = ''.join(filter(str.isdigit, range_parts[0]))
        start_row = int(start_row_str) if start_row_str else 1
        
        # Get all values in the specified column
        column_range = f"{column}{start_row}:{column}{start_row + len(used_range['values']) - 1}"
        column_data = self.get_range(workbook_item_id, worksheet_id, column_range, drive_id)
        
        if not column_data or "values" not in column_data:
            logger.warning(f"Failed to retrieve data from column {column}")
            return None
            
        # Search for value in column
        for i, cell in enumerate(column_data["values"]):
            cell_value = cell[0] if cell else None
            
            if cell_value is not None:
                if case_sensitive:
                    if str(cell_value) == str(search_value):
                        row_index = start_row + i
                        logger.info(f"Found value '{search_value}' at row {row_index}")
                        return row_index
                else:
                    if str(cell_value).lower() == str(search_value).lower():
                        row_index = start_row + i
                        logger.info(f"Found value '{search_value}' at row {row_index}")
                        return row_index
                        
        logger.warning(f"Value '{search_value}' not found in column {column}")
        return None
    
    def update_cell(self, workbook_item_id: str, worksheet_id: str, cell_address: str, 
                  value: Any, drive_id: str = None) -> bool:
        """
        Update a single cell value.
        
        Args:
            workbook_item_id (str): The ID of the workbook item
            worksheet_id (str): The ID or name of the worksheet
            cell_address (str): The cell address (e.g. 'A1')
            value (Any): The value to set
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not drive_id and not self.drive_id:
            logger.error("Drive ID is required")
            return False
            
        drive_id_to_use = drive_id or self.drive_id
        url = f"{self.base_url}/drives/{drive_id_to_use}/items/{workbook_item_id}/workbook/worksheets/{worksheet_id}/range(address='{cell_address}')"
        
        body = {
            "values": [[value]]
        }
        
        try:
            self._make_request("PATCH", url, json_data=body)
            logger.info(f"Updated cell {cell_address} with value: {value}")
            return True
        except:
            logger.error(f"Failed to update cell {cell_address}")
            return False
    
    def update_range(self, workbook_item_id: str, worksheet_id: str, range_address: str, 
                   values: List[List[Any]], drive_id: str = None) -> bool:
        """
        Update a range of cells.
        
        Args:
            workbook_item_id (str): The ID of the workbook item
            worksheet_id (str): The ID or name of the worksheet
            range_address (str): The range address (e.g. 'A1:B10')
            values (List[List[Any]]): The 2D array of values to set
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not drive_id and not self.drive_id:
            logger.error("Drive ID is required")
            return False
            
        drive_id_to_use = drive_id or self.drive_id
        url = f"{self.base_url}/drives/{drive_id_to_use}/items/{workbook_item_id}/workbook/worksheets/{worksheet_id}/range(address='{range_address}')"
        
        body = {
            "values": values
        }
        
        try:
            self._make_request("PATCH", url, json_data=body)
            logger.info(f"Updated range {range_address}")
            return True
        except:
            logger.error(f"Failed to update range {range_address}")
            return False
            
    def append_row(self, workbook_item_id: str, worksheet_id: str, values: List[Any], drive_id: str = None) -> bool:
        """
        Append a row to the end of a worksheet's data.
        
        Args:
            workbook_item_id (str): The ID of the workbook item
            worksheet_id (str): The ID or name of the worksheet
            values (List[Any]): The values to add as a new row
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            bool: True if successful, False otherwise
        """
        # First find the last row with data
        used_range = self.get_used_range(workbook_item_id, worksheet_id, drive_id)
        
        if not used_range or "values" not in used_range or not used_range["values"]:
            # If sheet is empty, start at row 1
            next_row = 1
        else:
            next_row = len(used_range["values"]) + 1  # Add to the row after the last used row
            
        # Determine how many columns we need
        num_columns = len(values)
        last_column_letter = self._column_letter(num_columns)
        
        # Create range address for the new row
        range_address = f"A{next_row}:{last_column_letter}{next_row}"
        
        # Update the range with the new row data
        return self.update_range(workbook_item_id, worksheet_id, range_address, [values], drive_id)
    
    def get_last_row(self, workbook_item_id: str, worksheet_id: str, drive_id: str = None) -> int:
        """
        Get the index of the last row with data.
        
        Args:
            workbook_item_id (str): The ID of the workbook item
            worksheet_id (str): The ID or name of the worksheet
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            int: The 1-based index of the last row with data
        """
        used_range = self.get_used_range(workbook_item_id, worksheet_id, drive_id)
        
        if not used_range or "values" not in used_range or not used_range["values"]:
            return 0
            
        return len(used_range["values"])
    
    def get_worksheet_dimensions(self, workbook_item_id: str, worksheet_id: str, drive_id: str = None) -> Tuple[int, int]:
        """
        Get the dimensions (rows and columns) of the worksheet's used range.
        
        Args:
            workbook_item_id (str): The ID of the workbook item
            worksheet_id (str): The ID or name of the worksheet
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            Tuple[int, int]: A tuple of (rows, columns) representing the dimensions
        """
        used_range = self.get_used_range(workbook_item_id, worksheet_id, drive_id)
        
        if not used_range or "values" not in used_range or not used_range["values"]:
            return (0, 0)
            
        rows = len(used_range["values"])
        cols = max(len(row) for row in used_range["values"]) if rows > 0 else 0
            
        logger.info(f"Worksheet dimensions: {rows} rows x {cols} columns")
        return (rows, cols)
    
    def download_workbook(self, workbook_name: str, local_path: str = None, drive_id: str = None) -> Optional[str]:
        """
        Download a workbook to a local file.
        
        Args:
            workbook_name (str): The name of the workbook
            local_path (str, optional): The local path to save to. If None, uses default pattern.
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            Optional[str]: The local file path if successful, None otherwise
        """
        workbook_item = self.get_workbook_by_name(workbook_name, drive_id=drive_id)
        
        if not workbook_item:
            logger.warning(f"Workbook '{workbook_name}' not found.")
            return None
            
        if not drive_id and not self.drive_id:
            logger.error("Drive ID is required")
            return None
            
        drive_id_to_use = drive_id or self.drive_id
        item_id = workbook_item["id"]
        
        url = f"{self.base_url}/drives/{drive_id_to_use}/items/{item_id}/content"
        
        try:
            response = requests.get(url, headers=self._headers())
            response.raise_for_status()
            
            if not local_path:
                self._check_download_folder()
                local_path = self._local_path(workbook_name)
                
            with open(local_path, 'wb') as file:
                file.write(response.content)
                
            logger.info(f"Downloaded workbook to {local_path}")
            return local_path
            
        except Exception as e:
            logger.error(f"Error downloading workbook: {str(e)}")
            return None
    
    def upload_workbook(self, local_path: str, upload_name: str = None, folder_path: str = "", drive_id: str = None) -> Optional[Dict]:
        """
        Upload a workbook to the drive.
        
        Args:
            local_path (str): The local file path
            upload_name (str, optional): The name to use when uploading. If None, uses the local filename.
            folder_path (str, optional): The folder path to upload to. Default is root.
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            Optional[Dict]: The created item if successful, None otherwise
        """
        if not os.path.exists(local_path):
            logger.error(f"Local file not found: {local_path}")
            return None
            
        if not drive_id and not self.drive_id:
            logger.error("Drive ID is required")
            return None
            
        drive_id_to_use = drive_id or self.drive_id
        
        # Use provided name or extract from path
        if not upload_name:
            upload_name = os.path.basename(local_path)
            
        if folder_path:
            url = f"{self.base_url}/drives/{drive_id_to_use}/root:/{self._safe_file_name(folder_path)}/{self._safe_file_name(upload_name)}:/content"
        else:
            url = f"{self.base_url}/drives/{drive_id_to_use}/root:/{self._safe_file_name(upload_name)}:/content"
            
        headers = self._headers()
        headers["Content-Type"] = "application/octet-stream"
        
        try:
            with open(local_path, 'rb') as file:
                response = requests.put(url, headers=headers, data=file)
                response.raise_for_status()
                
            result = response.json()
            logger.info(f"Uploaded workbook as {upload_name}")
            return result
            
        except Exception as e:
            logger.error(f"Error uploading workbook: {str(e)}")
            return None
    
    def find_row_by_id(self, workbook_item_id: str, worksheet_id: str, id_column: str, 
                     id_value: Any, drive_id: str = None) -> Optional[int]:
        """
        Find a row by ID value (specialized version of find_row_by_value).
        
        Args:
            workbook_item_id (str): The ID of the workbook item
            worksheet_id (str): The ID or name of the worksheet
            id_column (str): The column letter or header name containing IDs
            id_value (Any): The ID value to search for
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            Optional[int]: The 1-based row index if found, None otherwise
        """
        return self.find_row_by_value(workbook_item_id, worksheet_id, id_column, id_value, drive_id=drive_id)
    
    def create_worksheet(self, workbook_item_id: str, name: str, drive_id: str = None) -> Optional[Dict]:
        """
        Create a new worksheet in a workbook.
        
        Args:
            workbook_item_id (str): The ID of the workbook item
            name (str): The name for the new worksheet
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            Optional[Dict]: The created worksheet if successful, None otherwise
        """
        if not drive_id and not self.drive_id:
            logger.error("Drive ID is required")
            return None
            
        drive_id_to_use = drive_id or self.drive_id
        url = f"{self.base_url}/drives/{drive_id_to_use}/items/{workbook_item_id}/workbook/worksheets/add"
        
        body = {
            "name": name
        }
        
        try:
            result = self._make_request("POST", url, json_data=body)
            logger.info(f"Created worksheet: {name}")
            return result
        except:
            logger.error(f"Failed to create worksheet: {name}")
            return None

    def format_cells_as_hyperlinks(self, workbook_item_id: str, worksheet_id: str, 
                               range_address: str, urls: List[str], texts: List[str], 
                               drive_id: str = None) -> bool:
        """
        Format cells as hyperlinks using formulas.
        
        Args:
            workbook_item_id (str): The ID of the workbook item
            worksheet_id (str): The ID or name of the worksheet
            range_address (str): The range address for the hyperlinks
            urls (List[str]): List of URLs for the hyperlinks
            texts (List[str]): List of display texts for the hyperlinks
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            bool: True if successful, False otherwise
        """
        if len(urls) != len(texts):
            logger.error("URLs and texts lists must be the same length")
            return False
            
        # Create hyperlink formulas for each cell
        formulas = []
        for url, text in zip(urls, texts):
            # Escape double quotes in text and URL
            safe_text = text.replace('"', '""')
            safe_url = url.replace('"', '""')
            formulas.append([f'=HYPERLINK("{safe_url}", "{safe_text}")'])
            
        if not drive_id and not self.drive_id:
            logger.error("Drive ID is required")
            return False
            
        drive_id_to_use = drive_id or self.drive_id
        url = f"{self.base_url}/drives/{drive_id_to_use}/items/{workbook_item_id}/workbook/worksheets/{worksheet_id}/range(address='{range_address}')"
        
        body = {
            "formulas": formulas
        }
        
        try:
            self._make_request("PATCH", url, json_data=body)
            logger.info(f"Added {len(formulas)} hyperlinks to range {range_address}")
            return True
        except:
            logger.error(f"Failed to add hyperlinks to range {range_address}")
            return False
    
    def export_worksheet_to_csv(self, workbook_item_id: str, worksheet_id: str, local_path: str, drive_id: str = None) -> bool:
        """
        Export a worksheet to a local CSV file.
        
        Args:
            workbook_item_id (str): The ID of the workbook item
            worksheet_id (str): The ID or name of the worksheet
            local_path (str): The local path to save the CSV
            drive_id (str, optional): The drive ID. Uses instance drive_id if not provided.
            
        Returns:
            bool: True if successful, False otherwise
        """
        import csv
        
        # Get the used range of the worksheet
        used_range = self.get_used_range(workbook_item_id, worksheet_id, drive_id)
        
        if not used_range or "values" not in used_range or not used_range["values"]:
            logger.warning("No data found in worksheet")
            return False
            
        values = used_range.get("values", [])
        
        try:
            with open(local_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                for row in values:
                    writer.writerow(row)
                    
            logger.info(f"Exported worksheet to {local_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting to CSV: {str(e)}")
            return False
    
    def get_file_content(self, file_name):
        url = f"{self.DRIVES_PATH}/root:/{self.FILE_NAME_PARSE(file_name)}:/content"
        return self._make_request(url, "GET")    
    
    def get_file(self, file_name):
        url = f"{self.DRIVES_PATH}/root:/{self.FILE_NAME_PARSE(file_name)}"
        file_data = self._make_request(url, "GET")
        if "id" in file_data:
            return file_data["id"]
        else:
            return None
   

    def parse_deal_to_excel_sheet(
            self,
            workbook_id, 
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

            url = f"{self.items_path}/{workbook_id}/workbook/worksheets/{worksheet_name}/range(address='{target_range}')"
            body = {
                "values": values
            }

            
            try:
                result = self._make_request("PATCH", url, json_data=body)
                logger.info(f"updated excel sheet row.")
                return result
            except:
                logger.error(f"failed to update excel sheet row.")
                return None

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error {e.response.status_code} - {e.response.text}")
            return f"HTTP Error {e.response.status_code}"
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {str(e)}")
            return f"Request error: {str(e)}"
        


    def delete_row_by_id(self, workbook_id: str, worksheet_name: str, id_column: str, id_value: Any) -> bool:
        """
        Delete a row by finding it using an ID value.
        
        Args:
            workbook_id (str): The ID of the workbook
            worksheet_name (str): The name of the worksheet
            id_column (str): The column letter or header name containing IDs
            id_value (Any): The ID value to search for
            
        Returns:
            bool: True if row was found and deleted successfully, False otherwise
        """
        try:
            # Find the row by ID
            row_to_delete = self.find_row_by_id(workbook_id, worksheet_name, id_column, id_value)
            
            if row_to_delete is None:
                logger.warning(f"Row with ID '{id_value}' not found in column {id_column}")
                return False
                
            # Delete the found row
            return self.delete_row_by_number(workbook_id, worksheet_name, row_to_delete)
            
        except Exception as e:
            logger.error(f"Error deleting row by ID '{id_value}': {str(e)}")
            return False


    def delete_row_by_number(self, workbook_id: str, worksheet_name: str, row_number: int) -> bool:
        """
        Delete a specific row by its row number using the correct Microsoft Graph API method.
        
        Args:
            workbook_id (str): The ID of the workbook
            worksheet_name (str): The name of the worksheet
            row_number (int): The 1-based row number to delete
            
        Returns:
            bool: True if row was deleted successfully, False otherwise
        """
        try:
            # Use the correct Microsoft Graph API endpoint for deleting entire rows
            # This uses the deleteShift method which is the proper way to delete rows
            url = f"{self.items_path}/{workbook_id}/workbook/worksheets/{worksheet_name}/range(address='{row_number}:{row_number}')/delete"
            
            body = {
                "shift": "Up"  # Shift remaining rows up after deletion
            }
            
            # Make POST request to the delete endpoint
            result = self._make_request("POST", url, json_data=body)
            
            logger.info(f"Successfully deleted row {row_number} from worksheet {worksheet_name}")
            return True
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP Error {e.response.status_code} while deleting row {row_number}: {e.response.text}")
            return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error while deleting row {row_number}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error while deleting row {row_number}: {str(e)}")
            return False


    def delete_deal_from_excel_sheet(self, workbook_id: str, worksheet_name: str, deal_id: str) -> bool:
        """
        Delete a deal row from the Excel sheet by deal ID.
        
        Args:
            workbook_id (str): The ID of the workbook
            worksheet_name (str): The name of the worksheet
            deal_id (str): The deal ID to search for and delete
            
        Returns:
            bool: True if deal was found and deleted successfully, False otherwise
        """
        try:
            # Assuming deal_id is in column A (adjust as needed)
            return self.delete_row_by_id(workbook_id, worksheet_name, "A", deal_id)
            
        except Exception as e:
            logger.error(f"Error deleting deal '{deal_id}' from Excel sheet: {str(e)}")
            return False