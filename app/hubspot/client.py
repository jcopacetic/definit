import requests
import logging 
import json
import re
from datetime import datetime

from bs4 import BeautifulSoup as bs

logger = logging.getLogger(__name__)


def CLEAN_TEXT(text):
    text = re.sub(r'[^\x00-\x7F]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text


def FORMAT_DATE_1(date):
    if isinstance(date, datetime):
        dt = date
    elif isinstance(date, str):
        dt = datetime.strptime(date.rstrip("Z"), "%Y-%m-%dT%H:%M:%S.%f")
    else:
        raise TypeError("FORMAT_DATE_1 expected datetime or ISO string")

    return dt.strftime("%m/%d/%Y %I:%M:%S %p")


def FORMAT_DATE_2(date):
    if isinstance(date, datetime):
        dt = date
    elif isinstance(date, str):
        dt = datetime.strptime(date.rstrip("Z"), "%Y-%m-%dT%H:%M:%S.%f")
    else:
        raise TypeError("FORMAT_DATE_1 expected datetime or ISO string")

    return dt.strftime("%m/%d/%Y")


def FORMAT_TIMESTAMP_1(ms_timestamp: int) -> str:
    dt = datetime.fromtimestamp(ms_timestamp / 1000)
    return dt.strftime("%m/%d/%Y %I:%M:%S %p")


def FORMAT_TIMESTAMP_2(ms_timestamp: int) -> str:
    dt = datetime.fromtimestamp(ms_timestamp / 1000)
    return dt.strftime("%m/%d/%Y")


def CONVERT_STRING_TO_DATETIME(date_str):
    return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")


def FORMAT_CURRENCY(amount):
    if isinstance(amount, (int, float)):
        if isinstance(amount, float) and not amount.is_integer():
            return f"${amount:,.2f}"
        else:
            return f"${int(amount):,}"
    else:
        raise ValueError("Input must be an int or float")


class HubSpotClient: 

    def __init__(self):
        self.PORTAL_ID = "46658116"
        self.ACCESS_TOKEN = access_token

        self.BASE_URL = "https://api.hubapi.com"
        self.EMAILS_PATH = f"{self.BASE_URL}/crm/v3/objects/emails"
        self.DEALS_PATH = f"{self.BASE_URL}/crm/v3/objects/deals"
        self.CONTACTS_PATH = f"{self.BASE_URL}/crm/v3/objects/contacts"
        self.COMPANIES_PATH = f"{self.BASE_URL}/crm/v3/objects/companies"
        self.OWNERS_PATH = f"{self.BASE_URL}/crm/v3/owners"
        self.NOTES_PATH = f"{self.BASE_URL}/crm/v3/objects/notes"
        self.TASKS_PATH = f"{self.BASE_URL}/crm/v3/objects/tasks"
        self.QUOTES_PATH = f"{self.BASE_URL}/crm/v3/objects/quotes"
        self.ENGAGEMENTS_PATH = f"{self.BASE_URL}/engagements/v1/engagements"

        self.CONTACT_PROPS = {
            "firstname",
            "lastname",
            "email",
        }

        self.COMPANY_PROPS = {
            "name",
            "city",
            "state",
        }

        self.EMAIL_PROPS = {
            "hs_timestamp",
            "hubspot_owner_id",
            "hs_email_direction",
            "hs_email_html",
            "hs_email_status",
            "hs_email_subject",
            "hs_email_text",
            "hs_attachement_ids",
            "hs_email_headers",
            "from",
            "to",
        }

        self.NOTE_PROPS = {
            "hs_note_body",
            "hs_createdate",
            "hs_lastmodifieddate",
            "hs_object_id",
        }

        self.TASK_PROPS = {
            "hs_task_body",
            "hs_task_subject",
            "hs_task_priority",
            "hs_task_status",
            "hubspot_owner_id",
            "hs_timestamp",
        }

        self.DEAL_PROPS = {
            "dealname",
            "amount",
            "pipeline",
            "dealstage",
            "bidder_first_name",
            "bidder_last_name",
            "bidder_phone",
            "bidder_email",
            "link_to_plans",
            "hubspot_owner_id",
        }

        self.QUOTE_PROPS = {
            "hs_quote_amount",
            "hs_title",
            "hs_expiration_date",
            "publicUrl",
            "hs_quote_link",
        }

        self.ENGAGEMENT_PROPS = {
            "bodyPreview",
            "metadata",
            "type",
            "timestamp",
            "status",
            "ownerId",
            "createdAt",
            "lastUpdated",
            "engagement",
        }

    def BUILD_HEADERS(self):
        return {
            "Authorization": f"Bearer {self.ACCESS_TOKEN}",
            "Content-Type": "application/json",
        }

    def BUILD_DEAL_CONTACTS_ASSOC_PATH(self, deal_id):
        return f"{self.BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/contacts"

    def BUILD_DEAL_COMPANIES_ASSOC_PATH(self, deal_id, primary=False):
        if primary:
            return f"{self.BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/companies?associationType=5"
        else:
            return f"{self.BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/companies"

    def BUILD_DEAL_EMAIL_ASSOC_PATH(self, deal_id):
        return f"{self.BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/emails"

    def BUILD_DEAL_NOTES_ASSOC_PATH(self, deal_id):
        return f"{self.BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/notes"

    def BUILD_DEAL_TASKS_ASSOC_PATH(self, deal_id):
        return f"{self.BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/tasks"

    def BUILD_DEAL_QUOTES_ASSOC_PATH(self, deal_id):
        return f"{self.BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/quotes"

    def BUILD_DEAL_ENGAGEMENTS_ASSOC_PATH(self, deal_id):
        return f"{self.BASE_URL}/crm/v4/objects/deals/{deal_id}/associations/engagements"

    def BUILD_SALES_STAGES_PATH(self, pipeline_id):
        return f"{self.BASE_URL}/crm/v3/pipelines/0-3/{pipeline_id}/stages"

    def BUILD_URL_TO_PORTAL_DEAL(self, deal_id):
        return f"https://app.hubspot.com/contacts/{self.PORTAL_ID}/record/0-3/{deal_id}"

    def BUILD_URL_TO_WEBSITE_QUOTE(self, public_quote_id):
        return f"https://gohubsteel-46658116.hs-sites.com/{public_quote_id}"
    
    def _make_request(self, url, method="GET", params=None, body=None):
        """
        Centralized method to make HTTP requests to the HubSpot API
        
        Args:
            url (str): The URL to make the request to
            method (str, optional): HTTP method (GET, POST, PUT, PATCH, DELETE). Defaults to "GET".
            params (dict, optional): URL parameters. Defaults to None.
            body (dict, optional): Request body for POST/PUT/PATCH requests. Defaults to None.
            
        Returns:
            dict or None: JSON response if successful, None if error
        """
        try:
            logger.info(f"Making {method} request to: {url}")
        
            headers = self.BUILD_HEADERS()
            logger.info(f"Using Authorization: Bearer {self.ACCESS_TOKEN[:5]}...")
            
            if method.upper() == "GET":
                response = requests.get(url, headers=headers)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, params=params, json=body)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=headers, params=params, json=body)
            elif method.upper() == "PATCH":
                response = requests.patch(url, headers=headers, params=params, json=body)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=headers, params=params)
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

    def get_all_owners(self):
        """Get all owners from HubSpot"""
        url = f"{self.OWNERS_PATH}?limit=100&archived=true"
        
        owner_data = self._make_request(url, "GET")
        
        if not owner_data:
            logger.warning("No data returned for owners.")
        
        return owner_data
    
    def get_owner(self, owner_id):
        for archived_flag in [False, True]:
            url = f"{self.OWNERS_PATH}/{owner_id}"

            params = {"archived": str(archived_flag).lower()}

            owner_data = self._make_request(url, "GET", params=params)

            if not owner_data:
                logger.warning("No data returned for owners.")
        
        return owner_data
    

    def get_deal(self, deal_id, properties=None):
        """Get a specific deal by ID"""
        if properties is None:
            properties = self.DEAL_PROPS
            
        params = {"properties": list(properties)} if properties else None
        url = f"{self.DEALS_PATH}/{deal_id}"
        
        return self._make_request(url, "GET", params)
    
    def get_deals(self, properties=None, limit=30):
        """Get a specific deal by ID"""
        if properties is None:
            properties = self.DEAL_PROPS
            
        params = {"properties": list(properties)} if properties else None
        url = f"{self.DEALS_PATH}"
        
        response = self._make_request(url, "GET", params)
        deals_data = response.get("results")
        if not deals_data:
            return []
        return deals_data 

    def get_contacts_by_deal(self, deal_id):
        """Get contacts associated with a deal"""
        url = self.BUILD_DEAL_CONTACTS_ASSOC_PATH(deal_id)
        
        return self._make_request(url, "GET")
    
    def get_companies_by_deal(self, deal_id, primary=False):
        """Get companies associated with a deal"""
        url = self.BUILD_DEAL_COMPANIES_ASSOC_PATH(deal_id, primary)
        
        return self._make_request(url, "GET")
    
    def get_emails_by_deal(self, deal_id):
        """Get emails associated with a deal"""
        url = self.BUILD_DEAL_EMAIL_ASSOC_PATH(deal_id)
        
        return self._make_request(url, "GET")
    
    def get_notes_by_deal(self, deal_id):
        """Get notes associated with a deal"""
        url = self.BUILD_DEAL_NOTES_ASSOC_PATH(deal_id)
        
        return self._make_request(url, "GET")
    
    def get_tasks_by_deal(self, deal_id):
        """Get tasks associated with a deal"""
        url = self.BUILD_DEAL_TASKS_ASSOC_PATH(deal_id)
        
        return self._make_request(url, "GET")
    
    def get_quotes_by_deal(self, deal_id):
        """Get quotes associated with a deal"""
        url = self.BUILD_DEAL_QUOTES_ASSOC_PATH(deal_id)
        
        return self._make_request(url, "GET")
    
    def get_deal_associated_quotes(self, deal_id):
        url = self.BUILD_DEAL_QUOTES_ASSOC_PATH(deal_id)
        logger.info(f"Contstructed URL: {url}")

        response = self._make_request(url, "GET")

        deal_to_quotes_assoc_data = response.get("results", [])

        if not deal_to_quotes_assoc_data:
            logger.warning(f"No quotes retrieved for Deal: {deal_id}")
            return [] 
        
        quote_ids = []
        for assoc in deal_to_quotes_assoc_data: 
            quote_id = assoc.get("toObjectId") or assoc.get("id")
            if quote_id: 
                quote_ids.append(quote_id)
        
        logger.info(f"Found {len(quote_ids)} quotes for deal {deal_id}")
        return quote_ids
    
    def get_deal_associated_contacts(self, deal_id):
        url = self.BUILD_DEAL_CONTACTS_ASSOC_PATH(deal_id)
        deal_to_contacts_assoc_data = self._make_request(url, "GET").get("results", [])

        if not deal_to_contacts_assoc_data: 
            logger.warning(f"No contacts retrieved for Deal: {deal_id}")
            return []
        
        contact_ids = []
        for assoc in deal_to_contacts_assoc_data: 
            contact_id = assoc.get("toObjectId") or assoc.get("id")
            if contact_id: 
                contact_ids.append(contact_id)
        
        logger.info(f"found {len(contact_ids)} contacts for deal {deal_id}")

        return contact_ids 

    def get_deal_associated_companies(self, deal_id, primary=False):
        url = self.BUILD_DEAL_COMPANIES_ASSOC_PATH(deal_id, primary)
        deal_to_companies_assoc_data = self._make_request(url, "GET").get("results", [])
        
        if not deal_to_companies_assoc_data:
            logger.warning(f"No companies retrieved for Deal: {deal_id}")
            return [] 
        
        company_ids = []
        for assoc in deal_to_companies_assoc_data:
            company_id = assoc.get("toObjectId") or assoc.get("id")
            if company_id: 
                company_ids.append(company_id)
        
        logger.info(f"Found {len(company_ids)} companies for deal {deal_id}")
        return company_ids 


    def get_contact(self, contact_id, properties=None):
        """Get a specific contact by ID"""
        if properties is None:
            properties = self.CONTACT_PROPS
            
        params = {"properties": list(properties)} if properties else None
        url = f"{self.CONTACTS_PATH}/{contact_id}"
        
        return self._make_request(url, "GET", params)
    
    def get_company(self, company_id, properties=None):
        """Get a specific company by ID"""
        if properties is None:
            properties = self.COMPANY_PROPS
            
        params = {"properties": list(properties)} if properties else None
        url = f"{self.COMPANIES_PATH}/{company_id}"
        
        return self._make_request(url, "GET", params)
    
    def get_email(self, email_id, properties=None):
        """Get a specific email by ID"""
        if properties is None:
            properties = self.EMAIL_PROPS
            
        params = {"properties": list(properties)} if properties else None
        url = f"{self.EMAILS_PATH}/{email_id}"
        
        return self._make_request(url, "GET", params)
    
    def get_note(self, note_id, properties=None):
        """Get a specific note by ID"""
        if properties is None:
            properties = self.NOTE_PROPS
            
        params = {"properties": list(properties)} if properties else None
        url = f"{self.NOTES_PATH}/{note_id}"
        
        return self._make_request(url, "GET", params)
    
    def create_note(self, properties):
        """Create a new note"""
        url = self.NOTES_PATH
        body = {"properties": properties}
        
        return self._make_request(url, "POST", body=body)
    
    def update_deal(self, deal_id, properties):
        """Update properties of a deal"""
        url = f"{self.DEALS_PATH}/{deal_id}"
        body = {"properties": properties}
        
        return self._make_request(url, "PATCH", body=body)
    
    def associate_objects(self, from_object_type, from_object_id, to_object_type, to_object_id, association_type):
        """Create an association between two objects"""
        url = f"{self.BASE_URL}/crm/v4/associations/{from_object_type}/{from_object_id}/{to_object_type}/{to_object_id}"
        body = {"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": association_type}
        
        return self._make_request(url, "PUT", body=body)
    
    def search_objects(self, object_type, filter_groups=None, properties=None, limit=100):
        """Search for objects with filters"""
        url = f"{self.BASE_URL}/crm/v3/objects/{object_type}/search"
        
        body = {
            "filterGroups": filter_groups or [],
            "properties": properties,
            "limit": limit
        }
        
        return self._make_request(url, "POST", body=body)
    

    def get_engagement(self, engagement_id):
        url = f"{self.ENGAGEMENTS_PATH}/{engagement_id}"
        return self._make_request(url, "GET")


    def get_deal_associated_engagements(self, deal_id):

        url = self.BUILD_DEAL_ENGAGEMENTS_ASSOC_PATH(deal_id)

        response = self._make_request(url, "GET")
        results = response.get("results", [])
        if not results:
            logger.warning(f"No engagements retrieved for Deal: {deal_id}")
            return []

        engagement_ids = [
            assoc.get("toObjectId") or assoc.get("id") 
            for assoc in results 
            if assoc.get("toObjectId") or assoc.get("id")
        ]

        logger.info(f"Found {len(engagement_ids)} engagement(s) for deal {deal_id}")
        return engagement_ids


    def find_most_recent_engagement(self, deal_id):
        try:
            engagements = self.get_deal_associated_engagements(deal_id)
            if not engagements:
                logger.info(f"No engagements found for deal ID: {deal_id}")
                return {}

            engagement_collection = {
                "total_engagements": {
                    "latest_engagement": {}, 
                    "latest_engagement_date": 0, 
                    "latest_contact": {},
                    "latest_contact_date": 0,
                },
                "note_engagements": {"latest_note": {}, "latest_note_date": 0},
                "task_engagements": {"latest_task": {}, "latest_task_date": 0},
                "email_engagements": {"latest_email": {}, "latest_email_date": 0},
                "meeting_engagements": {"latest_meeting": {}, "latest_meeting_date": 0},
                "call_engagements": {"latest_call": {}, "latest_call_date": 0}
            }

            for eng_id in engagements:
                try:
                    engagement_data = self.get_engagement(str(eng_id))
                    engagement = engagement_data
                    engagement_type = engagement.get("engagement", {}).get("type", "")
                    engagement_date = engagement.get("engagement", {}).get("timestamp") or \
                    engagement.get("engagement", {}).get("lastUpdated") or \
                    engagement.get("engagement", {}).get("createdAt")

                    if not engagement_date:
                        logger.warning(f"No timestamp found for engagement ID: {eng_id}")
                        continue

                    # Total latest engagement
                    if engagement_date > engagement_collection["total_engagements"]["latest_engagement_date"]:
                        engagement_collection["total_engagements"].update({
                            "latest_engagement_date": engagement_date,
                            "latest_engagement": engagement_data
                        })

                    if engagement_type in ["EMAIL", "MEETING", "CALL"] and \
                        engagement_date > engagement_collection["total_engagements"]["latest_contact_date"]:
                        engagement_collection["total_engagements"].update({
                            "latest_contact_date": engagement_date,
                            "latest_contact": engagement_data,
                        })

                    # Type-specific latest engagement
                    type_key = f"{engagement_type.lower()}_engagements"
                    if type_key in engagement_collection:
                        date_key = f"latest_{engagement_type.lower()}_date"
                        if engagement_date > engagement_collection[type_key][date_key]:
                            engagement_collection[type_key][date_key] = engagement_date
                            engagement_collection[type_key][f"latest_{engagement_type.lower()}"] = engagement_data

                except Exception as e:
                    logger.exception(f"Failed to retrieve/process engagement ID {eng_id}")

            return engagement_collection

        except Exception as e:
            logger.exception(f"Error retrieving engagements for deal ID {deal_id}")
            return {}

    def get_latest_quote_public_url_key(self, deal_id):

        try:
            quote_ids = self.get_deal_associated_quotes(deal_id)
        except Exception as e:
            logger.exception(f"Failed to retrieve quotes for deal {deal_id}: {e}")
            return ("","")

        if not quote_ids:
            logger.info(f"No quotes found for deal {deal_id}.")
            return ("","")

        latest_quote_date = None

        for quote_id in quote_ids:
            try:
                quote = self.get_quote(quote_id)
                quote_properties = quote.get("properties", {})
                quote_created_str = quote_properties.get("hs_createdate")

                if not quote_created_str:
                    logger.debug(f"Missing 'hs_createdate' for quote {quote_id}. Skipping.")
                    continue

                quote_created_dt = CONVERT_STRING_TO_DATETIME(quote_created_str)

                if not latest_quote_date or quote_created_dt > latest_quote_date:
                    latest_quote_date = quote_created_dt
                    latest_quote_url = quote_properties.get("hs_quote_link")

            except ValueError as ve:
                logger.warning(f"Invalid datetime format for quote {quote_id}: {quote_created_str} — {ve}")
            except Exception as e:
                logger.exception(f"Error retrieving or processing quote {quote_id}: {e}")

        if not latest_quote_url:
            logger.warning(f"No valid public URL key found for any quote on deal {deal_id}.")
            return ("","")

        logger.info(f"Latest quote public URL key for deal {deal_id}: {latest_quote_url}")
        return (latest_quote_url, FORMAT_DATE_1(latest_quote_date)) if latest_quote_url else ("", "")


    def _parse_latest_engagement(self, data, key_type, key_date):
        latest = data.get("total_engagements", {})
        e_type = latest.get(key_type, {}).get("engagement", {}).get("type", "")
        timestamp_str = latest.get(key_date, 0)
        if timestamp_str:
            timestamp = FORMAT_TIMESTAMP_1(timestamp_str)
            return (e_type, timestamp) if e_type and timestamp else ("", "")
        return ("", "")


    def parse_last_contact(self, engagements):
        return self._parse_latest_engagement(engagements, "latest_contact", "latest_contact_date")

    def parse_last_engagement(self, engagements):
        return self._parse_latest_engagement(engagements, "latest_engagement", "latest_engagement_date")

    def get_stage_label(self, pipeline_id, stage_id):
        url = f"{self.BUILD_SALES_STAGES_PATH(pipeline_id)}/{stage_id}"
        stage_data = self._make_request(url, "GET")

        if not stage_data: 
            logger.warning(f"No stage received for ID: {stage_id} on pipeline ID: {pipeline_id}")
            return None

        stage_label = stage_data.get("label", "")

        if stage_label:
            return stage_label
        
        return None

    def parse_stage_label(self, properties):
        stage_id = properties.get("dealstage")
        pipeline_id = properties.get("pipeline")
        if stage_id and pipeline_id:
            return self.get_stage_label(pipeline_id, stage_id) or stage_id
        return stage_id or "Unknown Stage"


    def parse_deal_amount(self, amount_str):
        try:
            amount_int = int(amount_str)
            return str(FORMAT_CURRENCY(amount_int))
        except (ValueError, TypeError):
            return amount_str or ""

    def parse_owner(self, owner_id):
        owner = self.get_owner(owner_id)
        if not owner:
            return "Unknown Owner"
        archived = " (Deactivated User)" if owner.get("archived") else ""
        return f"{owner.get('firstName', '')} {owner.get('lastName', '')}{archived}".strip()

    def parse_contacts(self, deal_id):
        contacts = self.get_deal_associated_contacts(deal_id)
        contact_str = ""
        for contact_id in contacts:
            contact = self.get_contact(contact_id)
            if not contact:
                continue
            props = contact.get("properties", {})
            contact_str += f"{props.get('firstname', '')} {props.get('lastname', '')} ({props.get('email', '')}); "
        return contact_str.strip()

    def parse_company_info(self, deal_id):
        companies = self.get_deal_associated_companies(deal_id, primary=True)
        if not companies:
            return {}
        company = self.get_company(companies[0])
        if not company:
            return {}
        props = company.get("properties", {})
        return {
            "name": props.get("name", ""),
            "city": props.get("city", ""),
            "state": props.get("state", "")
        }


    def clean_html(self, raw_html: str, aggressive: bool = False) -> str:
        if not raw_html or not isinstance(raw_html, str):
            return raw_html
        
        soup = bs(raw_html, "html.parser")
        text = soup.get_text(separator=' ', strip=True)
        text = re.sub(r'\s+', ' ', text)

        if aggressive:
            text = ''.join(c for c in text if c.isprintable())

        return text
    
    def extract_preview(self, engagements, kind):
        kind_key = f"{kind}_engagements"
        latest_engagement = engagements.get(kind_key, {}).get(f"latest_{kind}", {})
        
        if not isinstance(latest_engagement, dict):
            return ""
        
        engagement_date = latest_engagement.get("engagement", {}).get("timestamp") or \
                    latest_engagement.get("engagement", {}).get("lastUpdated") or \
                    latest_engagement.get("engagement", {}).get("createdAt")

        preview = latest_engagement.get("bodyPreview", "") or latest_engagement.get("metadata", {}).get("bodyPreview", "")
        if preview:
            return f"{FORMAT_TIMESTAMP_1(engagement_date)} | {self.clean_html(preview)}"
        
        metadata = latest_engagement.get("metadata", {})
        engagement_type = latest_engagement.get("engagement", {}).get("type", "").upper()
        
        if engagement_type == "TASK":
            return f"{FORMAT_TIMESTAMP_1(engagement_date)} | {self.clean_html(metadata.get("subject", ""))}"
        elif engagement_type == "NOTE":
            return f"{FORMAT_TIMESTAMP_1(engagement_date)} | {self.clean_html(metadata.get("body", ""))}"
        elif engagement_type == "EMAIL":
            return f"{FORMAT_TIMESTAMP_1(engagement_date)} | {self.clean_html(metadata.get("text", "") or metadata.get("htmlContent", ""))}"
        elif engagement_type == "CALL":
            return f"{FORMAT_TIMESTAMP_1(engagement_date)} | {self.clean_html(metadata.get("body", "") or metadata.get("disposition", "") or metadata.get("status", ""))}"
        elif engagement_type == "MEETING":
            return f"{FORMAT_TIMESTAMP_1(engagement_date)} | {self.clean_html(metadata.get("body", "") or metadata.get("title", ""))}"

        return ""


    def collect_parse_all_deals_data(self, limit=30):
        try:
            logger.info(f"Collecting and parsing up to {limit} deals...")
            deals_info_and_egagements = {}
            deals = self.get_deals(limit)

            for deal in deals:
                deal_id = deal.get("id")
                if not deal_id:
                    logger.warning("Deal missing ID. Skipping.")
                    continue

                logger.info(f"Processing deal ID: {deal_id}")
                deal_properties = deal.get("properties", {})
                deal_engagements = self.find_most_recent_engagement(deal_id)

                if not deal_engagements.get("total_engagements", {}).get("latest_engagement"):
                    logger.info(f"No recent engagements for deal {deal_id}")
                    continue

                latest_quote_url = self.get_latest_quote_public_url_key(deal_id)

                last_contacted = self.parse_last_contact(deal_engagements)
                last_engagement = self.parse_last_engagement(deal_engagements)

                deal_data = {
                    "name": deal_properties.get("dealname", "Unknown Deal"),
                    "deal_link": self.BUILD_URL_TO_PORTAL_DEAL(deal_id),
                    "plans_link": deal_properties.get("amount", ""),
                    "quote_link": latest_quote_url[0],
                    "deal_stage": self.parse_stage_label(deal_properties),
                    "latest_bid_date": latest_quote_url[1],
                    "deal_amount": self.parse_deal_amount(deal_properties.get("amount")),
                    "deal_owner": self.parse_owner(deal_properties.get("hubspot_owner_id", "")),
                    "associated_contact": self.parse_contacts(deal_id),
                    "associated_company": "",
                    "city": "",
                    "state": "",
                    "last_contacted": last_contacted[1],
                    "last_contacted_type": last_contacted[0],
                    "last_engagement": last_engagement[1],
                    "last_engagement_type": last_engagement[0],
                    "email": self.extract_preview(deal_engagements, "email"),
                    "note": self.extract_preview(deal_engagements, "note"),
                    "task": self.extract_preview(deal_engagements, "task"),
                    "meeting": self.extract_preview(deal_engagements, "meeting"),
                    "call": self.extract_preview(deal_engagements, "call"),
                }

                company_info = self.parse_company_info(deal_id)
                deal_data["associated_company"] = company_info.get("name", "")
                deal_data["city"] = company_info.get("city", "")
                deal_data["state"] = company_info.get("state", "")

                deals_info_and_egagements[deal_id] = deal_data

            logger.info("Deal collection complete.")
            return deals_info_and_egagements

        except Exception as e:
            logger.exception("Error while building deals-emails collection")
            return None
        

    def collect_parse_deal_data(self, deal_id):
        try:
            logger.info(f"Collecting and parsing deal {deal_id}...")
            deals_info_and_egagements = {}
            deal = self.get_deal(deal_id)

            logger.info(f"from client: {deal}")

            deal_id = deal.get("id")
            if not deal_id:
                logger.warning("Deal missing ID. Skipping.")

            logger.info(f"Processing deal ID: {deal_id}")
            deal_properties = deal.get("properties", {})
            deal_engagements = self.find_most_recent_engagement(deal_id)

            if not deal_engagements.get("total_engagements", {}).get("latest_engagement"):
                logger.info(f"No recent engagements for deal {deal_id}")

            latest_quote_url = self.get_latest_quote_public_url_key(deal_id)

            last_contacted = self.parse_last_contact(deal_engagements)
            last_engagement = self.parse_last_engagement(deal_engagements)

            deal_data = {
                "name": deal_properties.get("dealname", "Unknown Deal"),
                "deal_link": self.BUILD_URL_TO_PORTAL_DEAL(deal_id),
                "plans_link": deal_properties.get("amount", ""),
                "quote_link": latest_quote_url[0],
                "deal_stage": self.parse_stage_label(deal_properties),
                "latest_bid_date": latest_quote_url[1],
                "deal_amount": self.parse_deal_amount(deal_properties.get("amount")),
                "deal_owner": self.parse_owner(deal_properties.get("hubspot_owner_id", "")),
                "associated_contact": self.parse_contacts(deal_id),
                "associated_company": "",
                "city": "",
                "state": "",
                "last_contacted": last_contacted[1],
                "last_contacted_type": last_contacted[0],
                "last_engagement": last_engagement[1],
                "last_engagement_type": last_engagement[0],
                "email": self.extract_preview(deal_engagements, "email"),
                "note": self.extract_preview(deal_engagements, "note"),
                "task": self.extract_preview(deal_engagements, "task"),
                "meeting": self.extract_preview(deal_engagements, "meeting"),
                "call": self.extract_preview(deal_engagements, "call"),
            }

            company_info = self.parse_company_info(deal_id)
            deal_data["associated_company"] = company_info.get("name", "")
            deal_data["city"] = company_info.get("city", "")
            deal_data["state"] = company_info.get("state", "")

            deals_info_and_egagements[deal_id] = deal_data

            logger.info("Deal collection complete.")
            return deals_info_and_egagements

        except Exception as e:
            logger.exception("Error while building deals-emails collection")
            return None
