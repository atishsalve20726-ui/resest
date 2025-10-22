import requests
import re
import json
import os
import asyncio
import aiohttp
from uuid import uuid4
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, InlineQueryHandler, filters, ContextTypes
import logging
from dotenv import load_dotenv
from typing import List, Tuple
from concurrent.futures import ThreadPoolExecutor
import time

# Load environment variables from .env file
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Constants
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
IG_APP_ID = '936619743392459'
CSRFTOKEN = 'umwHlWf6r3AGDowkZQb47m'

# Force join configuration
FORCE_CHANNEL_ID = os.getenv('FORCE_CHANNEL_ID')
FORCE_GROUP_ID = os.getenv('FORCE_GROUP_ID')
# Optional: Direct invite links (use these if bot is not admin in private groups)
FORCE_CHANNEL_INVITE_LINK = os.getenv('FORCE_CHANNEL_INVITE_LINK')
FORCE_GROUP_INVITE_LINK = os.getenv('FORCE_GROUP_INVITE_LINK')

# Admin configuration
ADMIN_ID = 5165555467

# User tracking with persistent storage
DATA_FILE = 'bot_data.json'
BACKUP_FILE = 'bot_data_backup.json'

# Initialize data structures
active_users = set()
user_stats = {
    'total_requests': 0,
    'bulk_requests': 0,
    'single_requests': 0,
    'bot_restarts': 0,
    'first_started': None,
    'last_restart': None
}

def load_data():
    """Load user data from JSON file"""
    global active_users, user_stats
    
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Load active users (convert list back to set)
            active_users = set(data.get('active_users', []))
            
            # Load user stats with defaults for new fields
            loaded_stats = data.get('user_stats', {})
            user_stats.update(loaded_stats)
            
            # Ensure all required fields exist
            if 'bot_restarts' not in user_stats:
                user_stats['bot_restarts'] = 0
            if 'first_started' not in user_stats:
                user_stats['first_started'] = time.time()
            
            # Update restart info
            user_stats['bot_restarts'] += 1
            user_stats['last_restart'] = time.time()
            
            logger.info(f"Data loaded: {len(active_users)} active users, {user_stats['total_requests']} total requests")
            logger.info(f"Bot restart #{user_stats['bot_restarts']}")
            
        else:
            # First time startup
            user_stats['first_started'] = time.time()
            user_stats['last_restart'] = time.time()
            user_stats['bot_restarts'] = 1
            logger.info("No existing data file found. Starting fresh.")
            
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        # Try backup file
        try:
            if os.path.exists(BACKUP_FILE):
                with open(BACKUP_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                active_users = set(data.get('active_users', []))
                user_stats.update(data.get('user_stats', {}))
                logger.info("Loaded data from backup file")
            else:
                logger.warning("No backup file available. Starting with empty data.")
        except Exception as e2:
            logger.error(f"Error loading backup: {e2}")

def save_data():
    """Save user data to JSON file with backup"""
    try:
        # Create backup of existing file
        if os.path.exists(DATA_FILE):
            import shutil
            shutil.copy2(DATA_FILE, BACKUP_FILE)
        
        # Prepare data for saving
        data = {
            'active_users': list(active_users),  # Convert set to list for JSON
            'user_stats': user_stats,
            'last_saved': time.time()
        }
        
        # Save to main file
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            
        logger.debug("Data saved successfully")
        
    except Exception as e:
        logger.error(f"Error saving data: {e}")

def auto_save_data():
    """Auto-save data every 5 minutes"""
    import threading
    
    def save_periodically():
        while True:
            time.sleep(300)  # 5 minutes
            save_data()
    
    # Start auto-save thread
    save_thread = threading.Thread(target=save_periodically, daemon=True)
    save_thread.start()
    logger.info("Auto-save enabled (every 5 minutes)")

# Performance configuration
MAX_CONCURRENT_BATCHES = 20  # Increased from 5 for high throughput
MAX_CONCURRENT_REQUESTS = 100  # Maximum concurrent HTTP requests
THREAD_POOL_SIZE = 50  # Thread pool for blocking operations
REQUEST_TIMEOUT = 10  # Timeout for HTTP requests
SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

# Global HTTP session for connection pooling
http_session = None
thread_pool = None

# Log force join configuration on startup
if FORCE_CHANNEL_ID or FORCE_GROUP_ID:
    logger.info(f"Force join enabled - Channel: {FORCE_CHANNEL_ID}, Group: {FORCE_GROUP_ID}")
else:
    logger.info("Force join is disabled - no channel/group configured")

async def method_1_async(email_or_username):
    """First password reset method - Async version"""
    url = 'https://www.instagram.com/accounts/account_recovery_send_ajax/'
    headers = {
        'User-Agent': USER_AGENT,
        'Referer': 'https://www.instagram.com/accounts/password/reset/',
        'X-CSRFToken': 'csrftoken'
    }
    data = {
        'email_or_username': email_or_username,
        'recaptcha_challenge_field': ''
    }
    
    async with SEMAPHORE:
        try:
            async with http_session.post(url, headers=headers, data=data, timeout=REQUEST_TIMEOUT) as response:
                return response.status, await response.text()
        except Exception as e:
            logger.warning(f"Method 1 error for {email_or_username}: {e}")
            return None, str(e)

def method_1(email_or_username):
    """First password reset method - Legacy sync version"""
    url = 'https://www.instagram.com/accounts/account_recovery_send_ajax/'
    headers = {
        'User-Agent': USER_AGENT,
        'Referer': 'https://www.instagram.com/accounts/password/reset/',
        'X-CSRFToken': 'csrftoken'
    }
    data = {
        'email_or_username': email_or_username,
        'recaptcha_challenge_field': ''
    }
    response = requests.post(url, headers=headers, data=data, timeout=REQUEST_TIMEOUT)
    return response

def extract_email(response_text):
    """Extract email from response"""
    match = re.search('<b>(.*?)</b>', response_text)
    if match:
        return match.group(1)
    else:
        return 'Unknown'

def parse_bulk_input(text: str) -> List[str]:
    """Parse input text to extract multiple usernames/emails"""
    # Split by various delimiters first
    items = []
    
    # First try splitting by newlines
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if line:
            # Then split each line by commas, semicolons, or spaces
            sub_items = re.split(r'[,;\s]+', line)
            for item in sub_items:
                item = item.strip()
                # Remove bot mentions (standalone @botname) but keep emails
                # If item starts with @ and doesn't contain a dot, it's a bot mention
                if item.startswith('@') and '.' not in item:
                    # Skip bot mentions
                    continue
                # Remove leading @ from bot mentions in mixed text
                if item.startswith('@') and '.' not in item:
                    item = item[1:]
                if item and len(item) > 2:  # Basic validation
                    items.append(item)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_items = []
    for item in items:
        if item.lower() not in seen:
            seen.add(item.lower())
            unique_items.append(item)
    
    return unique_items

async def method_3_async(username_or_email):
    """Third password reset method - Async version"""
    url = 'https://www.instagram.com/api/v1/web/accounts/account_recovery_send_ajax/'
    cookies = {
        'csrftoken': CSRFTOKEN,
        'datr': '_D1dZ0DhNw8dpOJHN-59ONZI',
        'ig_did': 'C0CBB4B6-FF17-4C4A-BB83-F3879B996720',
        'mid': 'Z109_AALAAGxFePISIe2H_ZcGwTD',
        'wd': '1157x959'
    }
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.5',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://www.instagram.com',
        'priority': 'u=1, i',
        'referer': 'https://www.instagram.com/accounts/password/reset/?source=fxcal&hl=en',
        'sec-ch-ua': '"Brave";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        'sec-ch-ua-full-version-list': '"Brave";v="131.0.0.0", "Chromium";v="131.0.0.0", "Not_A Brand";v="24.0.0.0"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-model': '""',
        'sec-ch-ua-platform': '"Windows"',
        'sec-ch-ua-platform-version': '"10.0.0"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'sec-gpc': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'x-asbd-id': '129477',
        'x-csrftoken': CSRFTOKEN,
        'x-ig-app-id': IG_APP_ID,
        'x-ig-www-claim': '0',
        'x-instagram-ajax': '1018880011',
        'x-requested-with': 'XMLHttpRequest',
        'x-web-session-id': 'ag36cv:1ko17s:9bxl9b'
    }
    data = {
        'email_or_username': username_or_email,
        'flow': 'fxcal'
    }
    
    async with SEMAPHORE:
        try:
            async with http_session.post(url, cookies=cookies, headers=headers, data=data, timeout=REQUEST_TIMEOUT) as response:
                result = await response.json()
                
                if result.get('status') == 'fail':
                    if result.get('error_type') == 'rate_limit_error':
                        return None, '⚠️ TRY USING VPN. IP LIMITED.'
                    elif 'message' in result and isinstance(result['message'], list):
                        return None, '❌ Check the username or email again.'
                    else:
                        return None, f"❌ An error occurred: {result.get('message', 'Unknown error')}"
                elif result.get('status') == 'ok':
                    return True, f"✅ Message: {result.get('message', 'No message provided')}"
                else:
                    return None, f"❌ Unexpected response: {result}"
        except Exception as e:
            logger.warning(f"Method 3 error for {username_or_email}: {e}")
            return None, f'❌ An unexpected error occurred: {str(e)}'

async def process_single_target_fast(username_or_email: str) -> Tuple[str, List[str]]:
    """High-performance async processing of a single username/email"""
    start_time = time.time()
    
    # Run all methods concurrently for maximum speed
    tasks = [
        method_1_async(username_or_email),
        method_2_async(username_or_email),
        method_3_async(username_or_email)
    ]
    
    results = []
    method_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Process Method 1 result
    try:
        method1_result = method_results[0]
        if isinstance(method1_result, Exception):
            results.append(f"❌ Method 1: Error - {str(method1_result)}")
        elif method1_result[0] == 200:
            email = extract_email(method1_result[1])
            results.append(f"✅ Method 1: PASSWORD RESET LINK SENT TO @{username_or_email} TO {email}")
        else:
            results.append(f"❌ Method 1: FAILED TO SEND PASSWORD RESET TO @{username_or_email}")
    except Exception as e:
        results.append(f"❌ Method 1: Error - {str(e)}")
    
    # Process Method 2 result
    try:
        method2_result = method_results[1]
        if isinstance(method2_result, Exception):
            results.append(f"❌ Method 2: Error - {str(method2_result)}")
        else:
            results.append(f"Method 2: {method2_result[1]}")
    except Exception as e:
        results.append(f"❌ Method 2: Error - {str(e)}")
    
    # Process Method 3 result
    try:
        method3_result = method_results[2]
        if isinstance(method3_result, Exception):
            results.append(f"❌ Method 3: Error - {str(method3_result)}")
        else:
            results.append(f"Method 3: {method3_result[1]}")
    except Exception as e:
        results.append(f"❌ Method 3: Error - {str(e)}")
    
    processing_time = time.time() - start_time
    logger.info(f"Processed {username_or_email} in {processing_time:.2f}s")
    
    return username_or_email, results

async def process_single_target(username_or_email: str) -> Tuple[str, List[str]]:
    """Legacy process_single_target for backward compatibility"""
    return await process_single_target_fast(username_or_email)

async def check_user_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> tuple[bool, list]:
    """Check if user is a member of required channel and group
    
    Allows users who are:
    - Full members (MEMBER)
    - Administrators (ADMINISTRATOR)
    - Owners (OWNER)
    - Pending approval (RESTRICTED - for join requests in private groups/channels)
    """
    not_joined = []
    
    # Valid statuses that allow bot usage
    allowed_statuses = [
        ChatMember.MEMBER,
        ChatMember.ADMINISTRATOR, 
        ChatMember.OWNER,
        ChatMember.RESTRICTED  # This covers pending join requests
    ]
    
    if FORCE_CHANNEL_ID:
        try:
            member = await context.bot.get_chat_member(chat_id=FORCE_CHANNEL_ID, user_id=user_id)
            logger.info(f"Channel membership check - User {user_id} status: {member.status}")
            
            # Check if user has any allowed status
            if member.status not in allowed_statuses:
                not_joined.append(('channel', FORCE_CHANNEL_ID))
                logger.info(f"User {user_id} NOT allowed in channel. Status: {member.status}")
            else:
                logger.info(f"User {user_id} allowed in channel with status: {member.status}")
        except Exception as e:
            logger.warning(f"Cannot check channel membership (bot may not be in channel): {e}")
            # If bot is not in the channel, we can't verify - allow user to proceed
            # This prevents blocking users when bot isn't added to the group
            pass
    
    if FORCE_GROUP_ID:
        try:
            member = await context.bot.get_chat_member(chat_id=FORCE_GROUP_ID, user_id=user_id)
            logger.info(f"Group membership check - User {user_id} status: {member.status}")
            
            # Check if user has any allowed status
            if member.status not in allowed_statuses:
                not_joined.append(('group', FORCE_GROUP_ID))
                logger.info(f"User {user_id} NOT allowed in group. Status: {member.status}")
            else:
                logger.info(f"User {user_id} allowed in group with status: {member.status}")
        except Exception as e:
            logger.warning(f"Cannot check group membership (bot may not be in group): {e}")
            # If bot is not in the group, we can't verify - allow user to proceed
            pass
    
    return len(not_joined) == 0, not_joined

async def create_join_keyboard(not_joined: list, context: ContextTypes.DEFAULT_TYPE) -> InlineKeyboardMarkup:
    """Create inline keyboard with join buttons"""
    keyboard = []
    
    for join_type, chat_id in not_joined:
        link = None
        
        # First, check if we have a direct invite link from environment variables
        if join_type == 'channel' and FORCE_CHANNEL_INVITE_LINK:
            link = FORCE_CHANNEL_INVITE_LINK
            logger.info(f"Using channel invite link from environment")
        elif join_type == 'group' and FORCE_GROUP_INVITE_LINK:
            link = FORCE_GROUP_INVITE_LINK
            logger.info(f"Using group invite link from environment")
        
        # If no direct link, try to get it from Telegram
        if not link:
            try:
                chat = await context.bot.get_chat(chat_id)
                # Try to get invite link if available
                if hasattr(chat, 'invite_link') and chat.invite_link:
                    link = chat.invite_link
                elif chat.username:
                    # If chat has a username, use it
                    link = f"https://t.me/{chat.username}"
                else:
                    # For private chats with numeric IDs, need to create/export invite link
                    # This requires the bot to be admin with invite permissions
                    try:
                        invite_link = await context.bot.export_chat_invite_link(chat_id)
                        link = invite_link
                    except Exception as e:
                        logger.warning(f"Cannot export invite link for {chat_id}: {e}")
                        # Fallback: try to construct link (may not work for private chats)
                        if str(chat_id).startswith('-100'):
                            # Remove -100 prefix for the link
                            link = f"https://t.me/c/{str(chat_id)[4:]}"
                        else:
                            link = f"https://t.me/c/{chat_id}"
            except Exception as e:
                logger.warning(f"Error getting chat info for {chat_id}: {e}")
                # Fallback link generation
                if isinstance(chat_id, str) and chat_id.startswith('@'):
                    link = f"https://t.me/{chat_id[1:]}"
                elif str(chat_id).startswith('-100'):
                    link = f"https://t.me/c/{str(chat_id)[4:]}"
                else:
                    link = f"https://t.me/{chat_id}"
        
        if join_type == 'channel':
            keyboard.append([InlineKeyboardButton("📢 Join Channel", url=link)])
        elif join_type == 'group':
            keyboard.append([InlineKeyboardButton("👥 Join Group", url=link)])
    
    keyboard.append([InlineKeyboardButton("✅ I've Joined", callback_data="check_membership")])
    
    return InlineKeyboardMarkup(keyboard)

async def method_2_async(username_or_email):
    """Second password reset method using Instagram API - Async version
    Note: This method only works with usernames, not emails"""
    
    # Check if input is an email address
    if '@' in username_or_email or '.' in username_or_email and not username_or_email.replace('.', '').replace('_', '').isalnum():
        # Skip Method 2 for email addresses as it requires username
        return None, f"⚠️ SKIPPED (Method 2 requires username, not email)"
    
    username = username_or_email
    
    # Clean up username (remove common email suffixes if accidentally included)
    for suffix in ['@gmail.com', '@yahoo.com', '@hotmail.com', '@outlook.com']:
        if suffix in username.lower():
            username = username.split(suffix)[0]
            break
    
    async with SEMAPHORE:
        try:
            # Get user ID
            profile_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
            headers = {
                'accept': '*/*',
                'accept-encoding': 'gzip',
                'accept-language': 'en-US;q=0.9,en;q=0.7',
                'referer': f"https://www.instagram.com/{username}",
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
                'x-ig-app-id': IG_APP_ID,
                'x-ig-www-claim': '0',
                'x-requested-with': 'XMLHttpRequest'
            }
            
            async with http_session.get(profile_url, headers=headers, timeout=REQUEST_TIMEOUT) as response:
                if response.status != 200:
                    return None, f"❌ FAILED TO SEND PASSWORD RESET TO @{username}"
                profile_data = await response.json()
                user_id = profile_data['data']['user']['id']
            
            # Send password reset
            reset_url = 'https://i.instagram.com/api/v1/accounts/send_password_reset/'
            reset_headers = {
                'User-Agent': 'Instagram 6.12.1 Android (30/11; 480dpi; 1080x2004; HONOR; ANY-LX2; HNANY-Q1; qcom; ar_EG_#u-nu-arab)',
                'Cookie': 'mid=YwsgcAABAAGsRwCKCbYCaUO5xej3; csrftoken=u6c8M4zaneeZBfR5scLVY43lYSIoUhxL',
                'Cookie2': '$Version=1',
                'Accept-Language': 'ar-EG, en-US',
                'X-IG-Connection-Type': 'MOBILE(LTE)',
                'X-IG-Capabilities': 'AQ==',
                'Accept-Encoding': 'gzip'
            }
            data = {
                'user_id': user_id,
                'device_id': str(uuid4())
            }
            
            async with http_session.post(reset_url, headers=reset_headers, data=data, timeout=REQUEST_TIMEOUT) as reset_response:
                if reset_response.status == 200:
                    reset_data = await reset_response.json()
                    obfuscated_email = reset_data.get('obfuscated_email', 'Unknown')
                    return True, f"✅ PASSWORD RESET LINK SENT TO @{username} AT {obfuscated_email}"
                else:
                    return None, f"❌ FAILED TO SEND PASSWORD RESET TO @{username}"
                    
        except Exception as e:
            logger.warning(f"Method 2 error for {username}: {e}")
            return None, f"❌ FAILED TO SEND PASSWORD RESET TO @{username}"

def method_2(username_or_email):
    """Second password reset method using Instagram API - Legacy sync version
    Note: This method only works with usernames, not emails"""
    
    # Check if input is an email address
    if '@' in username_or_email or '.' in username_or_email and not username_or_email.replace('.', '').replace('_', '').isalnum():
        # Skip Method 2 for email addresses as it requires username
        return None, f"⚠️ SKIPPED (Method 2 requires username, not email)"
    
    username = username_or_email
    
    # Clean up username (remove common email suffixes if accidentally included)
    for suffix in ['@gmail.com', '@yahoo.com', '@hotmail.com', '@outlook.com']:
        if suffix in username.lower():
            username = username.split(suffix)[0]
            break
    
    # Get user ID
    profile_url = f"https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
    headers = {
        'accept': '*/*',
        'accept-encoding': 'gzip',
        'accept-language': 'en-US;q=0.9,en;q=0.7',
        'referer': f"https://www.instagram.com/{username}",
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'x-ig-app-id': IG_APP_ID,
        'x-ig-www-claim': '0',
        'x-requested-with': 'XMLHttpRequest'
    }
    
    try:
        profile_response = requests.get(profile_url, headers=headers, timeout=REQUEST_TIMEOUT).json()
        user_id = profile_response['data']['user']['id']
    except:
        return None, f"❌ FAILED TO SEND PASSWORD RESET TO @{username}"
    
    # Send password reset
    reset_url = 'https://i.instagram.com/api/v1/accounts/send_password_reset/'
    headers = {
        'User-Agent': 'Instagram 6.12.1 Android (30/11; 480dpi; 1080x2004; HONOR; ANY-LX2; HNANY-Q1; qcom; ar_EG_#u-nu-arab)',
        'Cookie': 'mid=YwsgcAABAAGsRwCKCbYCaUO5xej3; csrftoken=u6c8M4zaneeZBfR5scLVY43lYSIoUhxL',
        'Cookie2': '$Version=1',
        'Accept-Language': 'ar-EG, en-US',
        'X-IG-Connection-Type': 'MOBILE(LTE)',
        'X-IG-Capabilities': 'AQ==',
        'Accept-Encoding': 'gzip'
    }
    data = {
        'user_id': user_id,
        'device_id': str(uuid4())
    }
    
    try:
        reset_response = requests.post(reset_url, headers=headers, data=data, timeout=REQUEST_TIMEOUT).json()
        obfuscated_email = reset_response['obfuscated_email']
        return True, f"✅ PASSWORD RESET LINK SENT TO @{username} AT {obfuscated_email}"
    except:
        return None, f"❌ FAILED TO SEND PASSWORD RESET TO @{username}"

def method_3(username_or_email):
    """Third password reset method"""
    url = 'https://www.instagram.com/api/v1/web/accounts/account_recovery_send_ajax/'
    cookies = {
        'csrftoken': CSRFTOKEN,
        'datr': '_D1dZ0DhNw8dpOJHN-59ONZI',
        'ig_did': 'C0CBB4B6-FF17-4C4A-BB83-F3879B996720',
        'mid': 'Z109_AALAAGxFePISIe2H_ZcGwTD',
        'wd': '1157x959'
    }
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.5',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://www.instagram.com',
        'priority': 'u=1, i',
        'referer': 'https://www.instagram.com/accounts/password/reset/?source=fxcal&hl=en',
        'sec-ch-ua': '"Brave";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        'sec-ch-ua-full-version-list': '"Brave";v="131.0.0.0", "Chromium";v="131.0.0.0", "Not_A Brand";v="24.0.0.0"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-model': '""',
        'sec-ch-ua-platform': '"Windows"',
        'sec-ch-ua-platform-version': '"10.0.0"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'sec-gpc': '1',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'x-asbd-id': '129477',
        'x-csrftoken': CSRFTOKEN,
        'x-ig-app-id': IG_APP_ID,
        'x-ig-www-claim': '0',
        'x-instagram-ajax': '1018880011',
        'x-requested-with': 'XMLHttpRequest',
        'x-web-session-id': 'ag36cv:1ko17s:9bxl9b'
    }
    data = {
        'email_or_username': username_or_email,
        'flow': 'fxcal'
    }
    
    try:
        response = requests.post(url, cookies=cookies, headers=headers, data=data)
        result = response.json()
        
        if result.get('status') == 'fail':
            if result.get('error_type') == 'rate_limit_error':
                return None, '⚠️ TRY USING VPN. IP LIMITED.'
            elif 'message' in result and isinstance(result['message'], list):
                return None, '❌ Check the username or email again.'
            else:
                return None, f"❌ An error occurred: {result.get('message', 'Unknown error')}"
        elif result.get('status') == 'ok':
            return True, f"✅ Message: {result.get('message', 'No message provided')}"
        else:
            return None, f"❌ Unexpected response: {result}"
    except json.JSONDecodeError:
        return None, '❌ Failed to parse the response as JSON.'
    except Exception as e:
        return None, f'❌ An unexpected error occurred: {str(e)}'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    
    # Track active user and save data
    if user_id not in active_users:
        active_users.add(user_id)
        save_data()  # Save when new user joins
    
    # Check if force join is enabled
    if FORCE_CHANNEL_ID or FORCE_GROUP_ID:
        is_member, not_joined = await check_user_membership(user_id, context)
        
        if not is_member:
            keyboard = await create_join_keyboard(not_joined, context)
            await update.message.reply_text(
                "🔒 *Access Restricted*\n\n"
                "To use this bot, you must join our channel and group first!\n\n"
                "Click the buttons below to join, then click 'I've Joined' to verify.",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            return
    
    # Short message for groups, full message for private chats
    if chat_type in ['group', 'supergroup']:
        welcome_message = (
            "⚡ *zEus x Raza - IG Reset Bot*\n\n"
            "Send username/email or multiple targets for bulk processing.\n"
            "Use /help for examples. By @Razaogz x @apolyte"
        )
    else:
        welcome_message = (
            "⚡ *zEus x Raza - Instagram Password Reset Bot*\n\n"
            "Welcome! This bot helps you send password reset links to Instagram accounts.\n\n"
            "📝 *How to use:*\n"
            "• Send a single username/email for individual processing\n"
            "• Send multiple targets for bulk processing (separated by lines, commas, or spaces)\n\n"
            "🚀 *New: Bulk Processing Support!*\n"
            "Process multiple accounts simultaneously with real-time progress tracking.\n\n"
            "Type /help for detailed usage examples.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👥 *Developers:*\n"
            "@Razaogz x @apolyte"
        )
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    chat_type = update.effective_chat.type
    
    # Short help for groups, detailed help for private chats
    if chat_type in ['group', 'supergroup']:
        help_message = (
            "📖 *Quick Help*\n\n"
            "*Usage:* Send username/email (single or multiple)\n"
            "*Examples:*\n"
            "• `username123`\n"
            "• `user1, user2, user3@email.com`\n\n"
            "DM me for detailed help. By @Razaogz x @apolyte"
        )
    else:
        help_message = (
            "📖 *Help - zEus x Raza Bot*\n\n"
            "*Commands:*\n"
            "/start - Start the bot\n"
            "/help - Show this help message\n\n"
            "*Single Target Usage:*\n"
            "Send any Instagram username or email address:\n"
            "`username123`\n"
            "`user@email.com`\n\n"
            "*🚀 Bulk Processing Usage:*\n"
            "Send multiple targets separated by:\n"
            "• New lines\n"
            "• Commas\n"
            "• Spaces\n\n"
            "*Bulk Examples:*\n"
            "```\n"
            "user1\n"
            "user2\n"
            "user3@email.com\n"
            "```\n"
            "Or: `user1, user2, user3@email.com`\n\n"
            "*Features:*\n"
            "🔄 Concurrent processing (batches of 5)\n"
            "📊 Real-time progress tracking\n"
            "📈 Summary reports\n"
            "⚡ Automatic duplicate removal\n\n"
            "*The bot uses 3 methods:*\n"
            "1️⃣ Basic account recovery\n"
            "2️⃣ API-based reset via user ID\n"
            "3️⃣ Web-based account recovery\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👥 *Developers:*\n"
            "@Razaogz x @apolyte"
        )
    
    await update.message.reply_text(help_message, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user messages containing username/email (supports bulk processing)."""
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    
    # Track active user
    if user_id not in active_users:
        active_users.add(user_id)
        save_data()  # Save when new user joins
    
    # If message is from a group/supergroup, only respond when bot is mentioned
    if chat_type in ['group', 'supergroup']:
        # Check if bot is mentioned in the message
        bot_username = context.bot.username
        message_text = update.message.text or ""
        
        # Check for @botusername mention or reply to bot's message
        is_mentioned = f"@{bot_username}" in message_text
        is_reply_to_bot = update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id
        
        if not (is_mentioned or is_reply_to_bot):
            # Ignore messages in groups where bot is not mentioned
            return
    
    # Check if force join is enabled
    if FORCE_CHANNEL_ID or FORCE_GROUP_ID:
        is_member, not_joined = await check_user_membership(user_id, context)
        
        if not is_member:
            keyboard = await create_join_keyboard(not_joined, context)
            await update.message.reply_text(
                "🔒 *Access Restricted*\n\n"
                "To use this bot, you must join our channel and group first!\n\n"
                "Click the buttons below to join, then click 'I've Joined' to verify.",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
            return
    
    input_text = update.message.text.strip()
    
    # Remove bot mention from the message if present
    if chat_type in ['group', 'supergroup']:
        bot_username = context.bot.username
        input_text = input_text.replace(f"@{bot_username}", "").strip()
    
    if not input_text:
        await update.message.reply_text("❌ Please provide a valid username or email.")
        return
    
    # Parse input to detect bulk requests
    targets = parse_bulk_input(input_text)
    
    if not targets:
        await update.message.reply_text("❌ No valid usernames or emails found in your message.")
        return
    
    # Determine if this is a bulk request
    is_bulk = len(targets) > 1
    
    if is_bulk:
        # Handle bulk processing
        user_stats['total_requests'] += 1
        user_stats['bulk_requests'] += 1
        save_data()  # Save stats update
        await handle_bulk_processing(update, targets)
    else:
        # Handle single target (original behavior)
        user_stats['total_requests'] += 1
        user_stats['single_requests'] += 1
        save_data()  # Save stats update
        await handle_single_processing(update, targets[0])

async def handle_single_processing(update: Update, target: str):
    """Handle processing for a single target"""
    # Send initial processing message
    processing_msg = await update.message.reply_text(
        f"🔄 Processing request for: `{target}`\n\n"
        "Attempting multiple password reset methods...",
        parse_mode='Markdown'
    )
    
    # Process the target
    username_or_email, results = await process_single_target(target)
    
    # Format results safely
    def escape_markdown_v2(text):
        """Escape special Markdown characters for safe display"""
        chars_to_escape = ['*', '_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in chars_to_escape:
            text = text.replace(char, f'\\{char}')
        return text
    
    formatted_results = []
    for result in results:
        # Escape the result text to prevent Markdown parsing errors
        safe_result = escape_markdown_v2(result)
        if "Method" in result:
            formatted_results.append(f"*{safe_result}*")
        else:
            formatted_results.append(safe_result)
    
    # Send final results
    final_message = "\n".join(formatted_results)
    safe_target = escape_markdown_v2(target)
    
    try:
        await processing_msg.edit_text(
            f"📊 *Results for:* `{safe_target}`\n\n{final_message}",
            parse_mode='MarkdownV2'
        )
    except Exception as e:
        logger.warning(f"Failed to edit message: {e}")
        # Try without markdown as fallback
        try:
            plain_results = "\n".join(results)
            await processing_msg.edit_text(
                f"📊 Results for: {target}\n\n{plain_results}"
            )
        except Exception as e2:
            logger.error(f"Failed to send results message: {e2}")

async def handle_bulk_processing(update: Update, targets: List[str]):
    """High-performance bulk processing for multiple targets"""
    total_targets = len(targets)
    start_time = time.time()
    
    # Send initial bulk processing message
    processing_msg = await update.message.reply_text(
        f"🚀 *High-Speed Bulk Processing Started*\n\n"
        f"📊 Total targets: {total_targets}\n"
        f"⚡ Max concurrent: {MAX_CONCURRENT_BATCHES}\n"
        f"⏳ Processing at maximum speed...\n\n"
        f"Progress: 0/{total_targets} completed",
        parse_mode='Markdown'
    )
    
    # Process targets in larger batches for maximum throughput
    batch_size = MAX_CONCURRENT_BATCHES
    completed = 0
    all_results = []
    
    for i in range(0, total_targets, batch_size):
        batch = targets[i:i + batch_size]
        batch_start_time = time.time()
        
        # Update progress
        try:
            await processing_msg.edit_text(
                f"🚀 *High-Speed Bulk Processing*\n\n"
                f"📊 Total targets: {total_targets}\n"
                f"⚡ Processing batch {i//batch_size + 1} ({len(batch)} targets)...\n"
                f"🔥 Speed: {MAX_CONCURRENT_BATCHES} concurrent\n\n"
                f"Progress: {completed}/{total_targets} completed",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Failed to update progress message: {e}")
        
        # Process batch with maximum concurrency
        batch_tasks = [process_single_target_fast(target) for target in batch]
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        
        # Collect results
        for j, result in enumerate(batch_results):
            if isinstance(result, Exception):
                all_results.append((batch[j], [f"❌ Error processing {batch[j]}: {str(result)}"]))
            else:
                all_results.append(result)
        
        completed += len(batch)
        batch_time = time.time() - batch_start_time
        
        # Update progress with performance metrics
        try:
            avg_time_per_target = batch_time / len(batch)
            targets_per_second = len(batch) / batch_time if batch_time > 0 else 0
            
            await processing_msg.edit_text(
                f"🚀 *High-Speed Bulk Processing*\n\n"
                f"📊 Total targets: {total_targets}\n"
                f"✅ Batch {i//batch_size + 1} completed in {batch_time:.1f}s\n"
                f"⚡ Speed: {targets_per_second:.1f} targets/sec\n"
                f"⏱️ Avg per target: {avg_time_per_target:.2f}s\n\n"
                f"Progress: {completed}/{total_targets} completed",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"Failed to update progress message: {e}")
        
        # Minimal delay for very large batches only
        if i + batch_size < total_targets and total_targets > 50:
            await asyncio.sleep(0.5)  # Reduced from 2 seconds
    
    # Generate summary report
    successful_count = 0
    failed_count = 0
    summary_lines = []
    
    for target, results in all_results:
        success_indicators = ["✅", "PASSWORD RESET LINK SENT"]
        has_success = any(any(indicator in result for indicator in success_indicators) for result in results)
        
        if has_success:
            successful_count += 1
            summary_lines.append(f"✅ {target}")
        else:
            failed_count += 1
            summary_lines.append(f"❌ {target}")
    
    # Calculate final performance metrics
    total_time = time.time() - start_time
    overall_speed = total_targets / total_time if total_time > 0 else 0
    
    # Create final summary message with performance stats (escape Markdown)
    def escape_markdown(text):
        """Escape special Markdown characters"""
        chars_to_escape = ['*', '_', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in chars_to_escape:
            text = text.replace(char, f'\\{char}')
        return text
    
    # Safely format results without breaking Markdown
    safe_results = []
    for line in summary_lines[:20]:
        safe_line = escape_markdown(line)
        safe_results.append(safe_line)
    
    summary_message = (
        f"🚀 *High\\-Speed Bulk Processing Complete*\n\n"
        f"📈 *Performance:*\n"
        f"• Total time: {total_time:.1f}s\n"
        f"• Overall speed: {overall_speed:.1f} targets/sec\n"
        f"• Concurrent batches: {MAX_CONCURRENT_BATCHES}\n\n"
        f"📊 *Summary:*\n"
        f"• Total processed: {total_targets}\n"
        f"• Successful: {successful_count}\n"
        f"• Failed: {failed_count}\n\n"
        f"*Results:*\n" + "\n".join(safe_results)
    )
    
    if len(summary_lines) > 20:
        summary_message += f"\n\n\\.\\.\\. and {len(summary_lines) - 20} more results"
    
    try:
        await processing_msg.edit_text(summary_message, parse_mode='MarkdownV2')
    except Exception as e:
        logger.warning(f"Failed to edit summary message with MarkdownV2: {e}")
        # Try with plain text as fallback
        try:
            plain_summary = (
                f"🚀 High-Speed Bulk Processing Complete\n\n"
                f"📈 Performance:\n"
                f"• Total time: {total_time:.1f}s\n"
                f"• Overall speed: {overall_speed:.1f} targets/sec\n"
                f"• Concurrent batches: {MAX_CONCURRENT_BATCHES}\n\n"
                f"📊 Summary:\n"
                f"• Total processed: {total_targets}\n"
                f"• Successful: {successful_count}\n"
                f"• Failed: {failed_count}\n\n"
                f"Results:\n" + "\n".join(summary_lines[:20])
            )
            if len(summary_lines) > 20:
                plain_summary += f"\n\n... and {len(summary_lines) - 20} more results"
            
            await processing_msg.edit_text(plain_summary)
        except Exception as e2:
            logger.error(f"Failed to send summary message: {e2}")
    
    # Send detailed results in chunks if requested (only in private chats)
    chat_type = update.effective_chat.type
    if total_targets <= 10 and chat_type == 'private':  # Only send detailed results in private chats
        try:
            detailed_message = "📋 Detailed Results:\n\n"
            for target, results in all_results[:5]:  # Limit to first 5 for message length
                detailed_message += f"{target}:\n"
                for result in results:
                    detailed_message += f"• {result}\n"
                detailed_message += "\n"
            
            if len(all_results) > 5:
                detailed_message += f"... and {len(all_results) - 5} more detailed results available"
            
            await update.message.reply_text(detailed_message)
        except Exception as e:
            logger.warning(f"Failed to send detailed results: {e}")

def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    return user_id == ADMIN_ID

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only stats command"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        # Silently ignore non-admin users
        return
    
    try:
        # Get basic bot stats
        bot_info = await context.bot.get_me()
        # Calculate uptime and format dates
        current_time = time.time()
        if user_stats.get('first_started'):
            total_uptime = current_time - user_stats['first_started']
            uptime_days = int(total_uptime // 86400)
            uptime_hours = int((total_uptime % 86400) // 3600)
            uptime_str = f"{uptime_days}d {uptime_hours}h"
        else:
            uptime_str = "Unknown"
        
        if user_stats.get('last_restart'):
            last_restart = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(user_stats['last_restart']))
        else:
            last_restart = "Unknown"
        
        stats_message = (
            f"📊 *Bot Statistics*\n\n"
            f"🤖 **Bot Info:**\n"
            f"• Name: {bot_info.first_name}\n"
            f"• Username: @{bot_info.username}\n"
            f"• ID: {bot_info.id}\n\n"
            f"👥 **User Statistics (Persistent):**\n"
            f"• Active Members: {len(active_users)}\n"
            f"• Total Requests: {user_stats['total_requests']}\n"
            f"• Bulk Requests: {user_stats['bulk_requests']}\n"
            f"• Single Requests: {user_stats['single_requests']}\n\n"
            f"🕐 **Uptime & Restarts:**\n"
            f"• Total Uptime: {uptime_str}\n"
            f"• Bot Restarts: {user_stats['bot_restarts']}\n"
            f"• Last Restart: {last_restart}\n"
            f"• Data Storage: ✅ JSON Files\n\n"
            f"⚙️ **Configuration:**\n"
            f"• Force Channel: {'✅' if FORCE_CHANNEL_ID else '❌'}\n"
            f"• Force Group: {'✅' if FORCE_GROUP_ID else '❌'}\n"
            f"• Admin ID: {ADMIN_ID}\n\n"
            f"🔧 **Features:**\n"
            f"• High-Speed Bulk Processing: ✅\n"
            f"• Max Concurrent Requests: {MAX_CONCURRENT_REQUESTS}\n"
            f"• Max Concurrent Batches: {MAX_CONCURRENT_BATCHES}\n"
            f"• Thread Pool Size: {THREAD_POOL_SIZE}\n"
            f"• Connection Pooling: ✅\n"
            f"• Async Processing: ✅\n"
            f"• Persistent Storage: ✅\n"
            f"• Auto-Save (5min): ✅\n\n"
            f"📈 **Status:** High-Performance Mode Active"
        )
        
        await update.message.reply_text(stats_message, parse_mode='Markdown')
        logger.info(f"Stats command used by admin {user_id}")
        
    except Exception as e:
        logger.error(f"Error in stats command: {e}")
        await update.message.reply_text("❌ Error retrieving stats.")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only broadcast command with improved error handling"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        # Silently ignore non-admin users
        return
    
    # Check if there's a message to broadcast
    if not context.args:
        await update.message.reply_text(
            "📢 *Broadcast Command*\n\n"
            "Usage: `/broadcast <message>`\n\n"
            "Example: `/broadcast Hello everyone! Bot is updated.`\n\n"
            "Note: This will send the message to all users who have interacted with the bot.",
            parse_mode='Markdown'
        )
        return
    
    broadcast_text = ' '.join(context.args)
    
    if not active_users:
        await update.message.reply_text(
            "📢 *Broadcast Status*\n\n"
            "❌ No active users to broadcast to.\n"
            "Users will be added to the list when they interact with the bot.",
            parse_mode='Markdown'
        )
        return
    
    # Send broadcast to all active users
    success_count = 0
    failed_count = 0
    blocked_count = 0
    forbidden_count = 0
    other_errors = 0
    
    initial_user_count = len(active_users)
    
    await update.message.reply_text(
        f"📢 *Broadcasting to {initial_user_count} users...*\n\n"
        f"Message: {broadcast_text}\n\n"
        f"⏳ Please wait, this may take a while...",
        parse_mode='Markdown'
    )
    
    # Track users to remove after iteration
    users_to_remove = set()
    
    for target_user_id in active_users.copy():  # Use copy to avoid modification during iteration
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"{broadcast_text}",
                parse_mode='Markdown'
            )
            success_count += 1
            
            # Add small delay to avoid hitting rate limits (30 messages per second)
            if success_count % 20 == 0:
                await asyncio.sleep(1)
                
        except Exception as e:
            error_msg = str(e).lower()
            
            # Categorize errors
            if "bot was blocked" in error_msg or "user is deactivated" in error_msg:
                blocked_count += 1
                users_to_remove.add(target_user_id)
                logger.info(f"User {target_user_id} blocked the bot or deactivated account")
            elif "bot can't initiate conversation" in error_msg or "forbidden" in error_msg:
                forbidden_count += 1
                users_to_remove.add(target_user_id)
                logger.info(f"Cannot initiate conversation with user {target_user_id} (never started bot)")
            else:
                other_errors += 1
                logger.warning(f"Failed to send broadcast to user {target_user_id}: {e}")
            
            failed_count += 1
    
    # Remove inactive users after iteration
    for user_id_to_remove in users_to_remove:
        active_users.discard(user_id_to_remove)
    
    # Save updated user list
    save_data()
    
    # Send detailed results to admin
    result_message = (
        f"📊 *Broadcast Complete*\n\n"
        f"✅ Successfully sent: {success_count}\n"
        f"❌ Total failed: {failed_count}\n\n"
        f"📋 *Failure Breakdown:*\n"
        f"• Blocked/Deactivated: {blocked_count}\n"
        f"• Never started bot: {forbidden_count}\n"
        f"• Other errors: {other_errors}\n\n"
        f"👥 *User List Updated:*\n"
        f"• Before: {initial_user_count} users\n"
        f"• After: {len(active_users)} users\n"
        f"• Removed: {len(users_to_remove)} inactive users\n\n"
        f"💾 Data saved automatically.\n\n"
        f"ℹ️ *Note:* Users who blocked the bot or never started it have been removed from the list."
    )
    
    await update.message.reply_text(result_message, parse_mode='Markdown')
    logger.info(f"Broadcast completed by admin {user_id}: {success_count} success, {failed_count} failed ({blocked_count} blocked, {forbidden_count} forbidden, {other_errors} other)")

async def save_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin-only manual save command"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        # Silently ignore non-admin users
        return
    
    try:
        save_data()
        
        # Get file info
        data_size = os.path.getsize(DATA_FILE) if os.path.exists(DATA_FILE) else 0
        backup_size = os.path.getsize(BACKUP_FILE) if os.path.exists(BACKUP_FILE) else 0
        
        save_message = (
            f"💾 *Data Saved Successfully*\n\n"
            f"📊 **Current Data:**\n"
            f"• Active Users: {len(active_users)}\n"
            f"• Total Requests: {user_stats['total_requests']}\n"
            f"• Bot Restarts: {user_stats['bot_restarts']}\n\n"
            f"📁 **File Info:**\n"
            f"• Main File: {data_size} bytes\n"
            f"• Backup File: {backup_size} bytes\n"
            f"• Auto-save: Every 5 minutes\n\n"
            f"✅ All data is now persistent!"
        )
        
        await update.message.reply_text(save_message, parse_mode='Markdown')
        logger.info(f"Manual save command used by admin {user_id}")
        
    except Exception as e:
        logger.error(f"Error in save command: {e}")
        await update.message.reply_text("❌ Error saving data.")

async def check_membership_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the 'I've Joined' button callback"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    # Check membership again
    is_member, not_joined = await check_user_membership(user_id, context)
    
    if is_member:
        # User has joined, show welcome message
        welcome_message = (
            "✅ *Verification Successful!*\n\n"
            "⚡ *zEus x Raza - Instagram Password Reset Bot*\n\n"
            "Welcome! This bot helps you send password reset links to Instagram accounts.\n\n"
            "📝 *How to use:*\n"
            "• Send a single username/email for individual processing\n"
            "• Send multiple targets for bulk processing (separated by lines, commas, or spaces)\n\n"
            "🚀 *New: Bulk Processing Support!*\n"
            "Process multiple accounts simultaneously with real-time progress tracking.\n\n"
            "Type /help for detailed usage examples.\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👥 *Developers:*\n"
            "@Razaogz x @apolyte"
        )
        await query.edit_message_text(welcome_message, parse_mode='Markdown')
    else:
        # User hasn't joined yet
        keyboard = await create_join_keyboard(not_joined, context)
        await query.edit_message_text(
            "❌ *Not Verified!*\n\n"
            "You haven't joined all required channels/groups yet.\n\n"
            "Please join them first, then click 'I've Joined' again.",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline queries for Instagram password reset."""
    query = update.inline_query.query.strip()
    user_id = update.effective_user.id
    
    # Track active user
    if user_id not in active_users:
        active_users.add(user_id)
        save_data()
    
    # If query is empty, show usage instructions
    if not query:
        results = [
            InlineQueryResultArticle(
                id=str(uuid4()),
                title="📝 How to use",
                description="Type Instagram username or email to send password reset",
                input_message_content=InputTextMessageContent(
                    message_text="⚡ *zEus x Raza - IG Reset Bot*\n\n"
                                 "Type @{} followed by an Instagram username or email to send a password reset link.\n\n"
                                 "Example: `@{} username123`\n\n"
                                 "By @Razaogz x @apolyte".format(
                                     context.bot.username,
                                     context.bot.username
                                 ),
                    parse_mode='Markdown'
                )
            )
        ]
        await update.inline_query.answer(results, cache_time=0)
        return
    
    # Parse input for single or multiple targets
    targets = parse_bulk_input(query)
    
    if not targets:
        results = [
            InlineQueryResultArticle(
                id=str(uuid4()),
                title="❌ Invalid Input",
                description="No valid usernames or emails found",
                input_message_content=InputTextMessageContent(
                    message_text="❌ No valid usernames or emails found in your query. Please try again."
                )
            )
        ]
        await update.inline_query.answer(results, cache_time=0)
        return
    
    # Update stats
    user_stats['total_requests'] += 1
    if len(targets) > 1:
        user_stats['bulk_requests'] += 1
    else:
        user_stats['single_requests'] += 1
    save_data()
    
    # Process targets asynchronously
    results_list = []
    
    # Limit to first 10 targets for inline queries to avoid timeout
    limited_targets = targets[:10]
    
    # Process all targets concurrently
    tasks = [process_single_target_fast(target) for target in limited_targets]
    processed_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Create inline results for each target
    for i, result in enumerate(processed_results):
        if isinstance(result, Exception):
            target = limited_targets[i]
            results_list.append(
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title=f"❌ Error: {target}",
                    description=f"Failed to process {target}",
                    input_message_content=InputTextMessageContent(
                        message_text=f"❌ Error processing {target}: {str(result)}"
                    )
                )
            )
        else:
            target, method_results = result
            
            # Determine if any method was successful
            success_indicators = ["✅", "PASSWORD RESET LINK SENT"]
            has_success = any(any(indicator in res for indicator in success_indicators) for res in method_results)
            
            # Create result summary
            result_text = f"📊 *Results for:* `{target}`\n\n"
            for method_result in method_results:
                result_text += f"{method_result}\n"
            result_text += "\n━━━━━━━━━━━━━━━━━━━━\nBy @Razaogz x @apolyte"
            
            # Create inline result
            if has_success:
                title = f"✅ {target}"
                description = "Password reset sent successfully"
            else:
                title = f"❌ {target}"
                description = "Failed to send password reset"
            
            results_list.append(
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title=title,
                    description=description,
                    input_message_content=InputTextMessageContent(
                        message_text=result_text,
                        parse_mode='Markdown'
                    )
                )
            )
    
    # If more than 10 targets, add a note
    if len(targets) > 10:
        results_list.append(
            InlineQueryResultArticle(
                id=str(uuid4()),
                title=f"ℹ️ {len(targets) - 10} more targets",
                description="Inline queries are limited to 10 targets. Use private chat for bulk processing.",
                input_message_content=InputTextMessageContent(
                    message_text=f"ℹ️ You have {len(targets) - 10} more targets.\n\n"
                                 f"Inline queries are limited to 10 targets at a time.\n\n"
                                 f"For bulk processing of more targets, please use the bot in private chat.\n\n"
                                 f"By @Razaogz x @apolyte"
                )
            )
        )
    
    # Answer the inline query
    await update.inline_query.answer(results_list, cache_time=0)
    logger.info(f"Inline query processed for user {user_id}: {len(limited_targets)} targets")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors caused by updates."""
    error = context.error
    logger.error(f'Update {update} caused error {error}')
    
    # Only send error message for critical errors, not for handled exceptions
    # Skip certain error types that are handled within the application
    skip_error_types = [
        'BadRequest',  # Usually handled within message editing
        'TimedOut',    # Network timeouts are common and handled
        'NetworkError' # Network issues are temporary
    ]
    
    error_type = type(error).__name__
    if error_type not in skip_error_types and update and update.message:
        try:
            await update.message.reply_text(
                "❌ An unexpected error occurred. Please try again or contact support if the issue persists."
            )
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")

async def init_http_session():
    """Initialize HTTP session for high-performance requests"""
    global http_session, thread_pool
    
    # Create aiohttp session with optimized settings
    connector = aiohttp.TCPConnector(
        limit=MAX_CONCURRENT_REQUESTS,  # Connection pool size
        limit_per_host=50,  # Max connections per host
        ttl_dns_cache=300,  # DNS cache TTL
        use_dns_cache=True,
        keepalive_timeout=30,
        enable_cleanup_closed=True
    )
    
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    
    http_session = aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        headers={'User-Agent': USER_AGENT}
    )
    
    # Create thread pool for blocking operations
    thread_pool = ThreadPoolExecutor(max_workers=THREAD_POOL_SIZE)
    
    logger.info(f"High-performance HTTP session initialized:")
    logger.info(f"• Max concurrent requests: {MAX_CONCURRENT_REQUESTS}")
    logger.info(f"• Max concurrent batches: {MAX_CONCURRENT_BATCHES}")
    logger.info(f"• Thread pool size: {THREAD_POOL_SIZE}")
    logger.info(f"• Request timeout: {REQUEST_TIMEOUT}s")

async def cleanup_http_session():
    """Cleanup HTTP session and thread pool"""
    global http_session, thread_pool
    
    if http_session:
        await http_session.close()
        logger.info("HTTP session closed")
    
    if thread_pool:
        thread_pool.shutdown(wait=True)
        logger.info("Thread pool shut down")

def main():
    """Start the high-performance bot."""
    # Get bot token from environment variable
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN not found!")
        print("Please create a .env file with your bot token.")
        print("See .env.example for reference.")
        return
    
    async def post_init(application):
        """Initialize high-performance components after bot startup"""
        # Load persistent data
        load_data()
        
        # Start auto-save
        auto_save_data()
        
        # Initialize HTTP session
        await init_http_session()
        
        logger.info("🚀 Bot initialization complete with persistent storage!")
    
    async def post_shutdown(application):
        """Cleanup high-performance components before bot shutdown"""
        # Save data before shutdown
        save_data()
        logger.info("💾 Data saved before shutdown")
        
        # Cleanup HTTP session
        await cleanup_http_session()
    
    # Create the Application with optimized settings
    application = (Application.builder()
                  .token(TOKEN)
                  .concurrent_updates(True)  # Enable concurrent update processing
                  .post_init(post_init)
                  .post_shutdown(post_shutdown)
                  .build())
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("brodcast", broadcast_command))  # Alias for broadcast
    application.add_handler(CommandHandler("save", save_command))  # Admin save command
    application.add_handler(CallbackQueryHandler(check_membership_callback, pattern="^check_membership$"))
    application.add_handler(InlineQueryHandler(inline_query))  # Inline query handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Register error handler
    application.add_error_handler(error_handler)
    
    # Start the bot
    logger.info("🚀 High-Performance Bot starting...")
    logger.info(f"⚡ Configured for {MAX_CONCURRENT_REQUESTS} concurrent requests")
    logger.info(f"🔥 Batch processing: {MAX_CONCURRENT_BATCHES} concurrent targets")
    print("🚀 High-Performance Bot is running... Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
