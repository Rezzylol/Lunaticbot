from utils import print_setup_instructions
import os
import logging
import re
import asyncio
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from solana.rpc.api import Client
from solders.keypair import Keypair
from base58 import b58decode

TELEGRAM_API_TOKEN = os.getenv('TELEGRAM_API_TOKEN')
GROUP_CHAT_ID = os.getenv('GROUP_CHAT_ID')
PRIVATE_KEY = os.getenv('PRIVATE_KEY')

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Set to store already processed addresses
processed_addresses = set()

# Initialize Solana client and wallet
solana_client = Client("https://api.mainnet-beta.solana.com")
wallet = None

def setup_wallet():
    global wallet
    if not PRIVATE_KEY:
        logger.error("PRIVATE_KEY is missing. Please set it in the Env Secrets tab.")
        return False
    
    try:
        private_key_bytes = b58decode(PRIVATE_KEY)
        wallet = Keypair.from_bytes(private_key_bytes)
        logger.info(f"Wallet initialized with public key: {wallet.pubkey()}")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize wallet: {str(e)}")
        return False

def is_valid_solana_address(address: str) -> bool:
    base58_regex = r'^[1-9A-HJ-NP-Za-km-z]{32,44}$'
    return bool(re.match(base58_regex, address))

async def execute_jupiter_swap(token_address: str) -> dict:
    # Jupiter API endpoint for quote
    quote_url = "https://quote-api.jup.ag/v6/quote"
    
    params = {
        "inputMint": "So11111111111111111111111111111111111111112",  # SOL
        "outputMint": token_address,
        "amount": "10000000",  # 0.01 SOL in lamports
        "slippageBps": 1500,   # 15% slippage
    }
    
    try:
        response = requests.get(quote_url, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error getting Jupiter quote: {str(e)}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_text(f'Hi {user.first_name}! Send me a Solana contract address to execute a swap.')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = """
Here are the commands I understand:
/start - Start the bot
/help - Show this help message

Just send me a Solana contract address and I'll try to swap 0.01 SOL for tokens!
"""
    await update.message.reply_text(help_text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages with contract addresses."""
    message_text = update.message.text.strip()
    
    if not is_valid_solana_address(message_text):
        await update.message.reply_text("This doesn't look like a valid Solana address. Please try again.")
        return
    
    if message_text in processed_addresses:
        await update.message.reply_text("This address has already been processed.")
        return
    
    processed_addresses.add(message_text)
    
    # Get Jupiter quote
    quote = await execute_jupiter_swap(message_text)
    if not quote:
        await update.message.reply_text("Failed to get quote from Jupiter. Please try again later.")
        return
    
    # Forward to group chat if configured
    if GROUP_CHAT_ID:
        try:
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"🚀 New Solana contract address received: `{message_text}`\nQuote received: {quote['outAmount']} tokens",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Failed to forward to group: {str(e)}")
    
    await update.message.reply_text(f"Processing swap for address: {message_text}\nQuote received: {quote['outAmount']} tokens")

async def setup_telegram_bot():
    if not TELEGRAM_API_TOKEN:
        logger.error("TELEGRAM_API_TOKEN is missing. Please set it in the Env Secrets tab.")
        print_setup_instructions()
        return None

    try:
        application = Application.builder().token(TELEGRAM_API_TOKEN).build()

        # Add command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))

        # Add message handler
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        logger.info("Bot has been set up successfully.")
        return application
    except Exception as e:
        logger.error(f"Failed to set up Telegram bot: {str(e)}")
        return None

async def run_telegram_bot(application):
    logger.info("Starting Telegram bot")
    await application.initialize()
    await application.start()
    await application.run_polling()

def main():
    # Set up the wallet first
    if not setup_wallet():
        logger.error("Failed to set up wallet. Exiting.")
        return
    
    # Set up and run the Telegram bot
    asyncio.run(setup_and_run_bot())

async def setup_and_run_bot():
    application = await setup_telegram_bot()
    if not application:
        logger.error("Failed to set up Telegram bot. Exiting.")
        return
    
    await run_telegram_bot(application)

if __name__ == "__main__":
    main()