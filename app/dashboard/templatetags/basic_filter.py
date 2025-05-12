import logging
from django import template
import re
from datetime import datetime
import json
from textwrap import shorten

register = template.Library()

logger = logging.getLogger(__name__)
# Existing filters

@register.filter(name='replace_underscores')
def replace_underscores(value):
    """
    Replaces all underscores in the input string with spaces.

    Usage in template:
        {{ some_text|replace_underscores }}
    """
    try:
        result = str(value).replace('_', ' ')
        logger.debug(f"Replaced underscores in '{value}' with spaces -> '{result}'")
        return result
    except Exception as e:
        logger.error(f"Error replacing underscores in value '{value}': {e}")
        return value

@register.filter(name='replace_text')
def replace_text(value, arg):
    """Replaces all occurrences of arg in value with an empty string."""
    return value.replace(arg, '')

@register.filter(name='find_replace')
def find_replace(text, replacement_clause):
    """Replaces specified values in a string.
    
    Args:
        text: The string to modify.
        replacement_clause: A string containing the value to find and its replacement, separated by a pipe (|).
                           Example: "old_value|new_value"
    
    Returns:
        A string with all occurrences of the value to find replaced by the new value.
    """
    try:
        old_value, new_value = replacement_clause.split('|', 1)
        return text.replace(old_value, new_value)
    except ValueError:
        return text

# New enhanced filters

@register.filter(name='regex_replace')
def regex_replace(text, replacement_clause):
    """Replaces text using regular expressions.
    
    Args:
        text: The string to modify.
        replacement_clause: A string containing the regex pattern and replacement, separated by a pipe (|).
                           Example: "pattern|replacement"
    
    Returns:
        A string with all regex matches replaced.
    """
    try:
        pattern, replacement = replacement_clause.split('|', 1)
        return re.sub(pattern, replacement, text)
    except (ValueError, re.error):
        return text

@register.filter(name='truncate_chars')
def truncate_chars(text, length):
    """Truncates text to specified length and adds ellipsis if necessary.
    
    Args:
        text: The text to truncate.
        length: Maximum length of the result string.
    
    Returns:
        Truncated string with ellipsis if truncation occurred.
    """
    try:
        length = int(length)
        if len(text) <= length:
            return text
        return shorten(text, width=length, placeholder="...")
    except (ValueError, TypeError):
        return text

@register.filter(name='default_if_none')
def default_if_none(value, default):
    """Returns default value if the value is None.
    
    Args:
        value: The value to check.
        default: The default value to return if value is None.
    
    Returns:
        Either the original value or the default.
    """
    return default if value is None else value

@register.filter(name='date_format')
def date_format(value, format_string="%B %d, %Y"):
    """Formats a date using specified format string.
    
    Args:
        value: A datetime object or string.
        format_string: The format string to use (default: '%B %d, %Y').
    
    Returns:
        A formatted date string.
    """
    if not value:
        return ''
    
    if not isinstance(value, datetime):
        try:
            # Attempt to parse ISO format date
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except (ValueError, AttributeError, TypeError):
            return value
    
    try:
        return value.strftime(format_string)
    except (ValueError, TypeError):
        return value

@register.filter(name='jsonify')
def jsonify(obj):
    """Converts a Python object to JSON string.
    
    Args:
        obj: The object to serialize.
    
    Returns:
        A JSON string representation of the object.
    """
    try:
        return json.dumps(obj)
    except (TypeError, ValueError):
        return '{}'



@register.filter(name='pluralize_custom')
def pluralize_custom(value, arg='s'):
    """Returns a plural suffix if the value is not 1.
    
    Args:
        value: The value to check.
        arg: The plural suffix to use, can be a string with singular and plural 
             suffixes separated by a comma.
    
    Returns:
        Appropriate suffix based on value.
    """
    try:
        value = int(value)
        if ',' in arg:
            singular, plural = arg.split(',')
            return singular if value == 1 else plural
        else:
            return '' if value == 1 else arg
    except (ValueError, TypeError):
        return ''

@register.filter(name='phone_format')
def phone_format(number):
    """Formats a phone number string.
    
    Args:
        number: A string representing a phone number.
    
    Returns:
        A formatted phone number in the format: (XXX) XXX-XXXX
    """
    if not number:
        return ''
    
    # Remove any non-digit characters
    clean_number = re.sub(r'\D', '', str(number))
    
    # Format the number
    if len(clean_number) == 10:
        return f"({clean_number[:3]}) {clean_number[3:6]}-{clean_number[6:]}"
    elif len(clean_number) == 11 and clean_number[0] == '1':
        return f"({clean_number[1:4]}) {clean_number[4:7]}-{clean_number[7:]}"
    else:
        return number

@register.filter(name='currency')
def currency(value, currency_symbol='$'):
    """Formats a number as currency.
    
    Args:
        value: The numeric value to format.
        currency_symbol: The currency symbol to use (default: $).
    
    Returns:
        A formatted currency string.
    """
    try:
        value = float(value)
        formatted = f"{value:,.2f}"
        return f"{currency_symbol}{formatted}"
    except (ValueError, TypeError):
        return value

@register.filter(name='list_join')
def list_join(value, separator=', '):
    """Joins a list of items with the specified separator.
    
    Args:
        value: A list or iterable to join.
        separator: The string to use as a separator (default: ', ').
    
    Returns:
        A string with the joined elements.
    """
    if not value:
        return ''
    
    try:
        return separator.join(str(item) for item in value)
    except (TypeError, AttributeError):
        return value

@register.filter(name='get_item')
def get_item(dictionary, key):
    """Gets an item from a dictionary by key.
    
    Args:
        dictionary: The dictionary to search.
        key: The key to look up.
    
    Returns:
        The value for the specified key or None if the key doesn't exist.
    """
    if not dictionary:
        return None
    
    try:
        return dictionary.get(key)
    except (AttributeError, TypeError):
        return None