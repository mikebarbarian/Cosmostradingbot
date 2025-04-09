import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import threading
import time
import json
import subprocess
from datetime import datetime
import os

class OsmosisClient:
    """Simple client for interacting with Osmosis"""
    
    def __init__(self, root=None):
        # Wallet information
        self.wallet_name = "cl"  # Your wallet name
        self.wallet_address = "osmo1yjamm9zkmqmyvqc5wjfha9egg4r4ha9nzkvpsd"
        self.root = root

        # Initialize with the correct pool IDs and token denominations
        self.pools = {
            "OSMO/USDC": {
                "pool_id": "1464", 
                "base_denom": "uosmo", 
                "quote_denom": "ibc/498A0751C798A0D9A389AA3691123DADA57DAA4FE165D5C75894505B876BA6E4"
            },
            "BTC/USDC": {
                "pool_id": "1943", 
                "base_denom": "factory/osmo1z6r6qdknhgsc0zeracktgpcxf43j6sekq07nw8sxduc9lg0qjjlqfu25e3/alloyed/allBTC", 
                "quote_denom": "ibc/498A0751C798A0D9A389AA3691123DADA57DAA4FE165D5C75894505B876BA6E4"
            },
            "ETH/USDC": {
                "pool_id": "1948", 
                "base_denom": "factory/osmo1k6c8jln7ejuqwtqmay3yvzrg3kueaczl96pk067ldg8u835w0yhsw27twm/alloyed/allETH", 
                "quote_denom": "ibc/498A0751C798A0D9A389AA3691123DADA57DAA4FE165D5C75894505B876BA6E4"
            },
        }

        self.balances = {
            "USDC": 0,
            "OSMO": 0,
            "BTC": 0,
            "ETH": 0
        }
        self.last_balance_update = 0

    def get_wallet_balances(self, force_update=False):
        """Get current wallet balances with caching"""
        # Only update once per hour unless forced
        if not force_update and time.time() - self.last_balance_update < 3600:
            return self.balances
            
        try:
            cmd = ["osmosisd", "q", "bank", "balances", self.wallet_address, "--output", "json"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                balances = json.loads(result.stdout)['balances']
                
                # Reset all balances first
                self.balances = {k: 0 for k in self.balances}
                
                # Parse balances
                for balance in balances:
                    amount = balance['amount']
                    denom = balance['denom']
                    
                    if denom == "uosmo":
                        self.balances["OSMO"] = float(amount) / 1_000_000
                    elif "allBTC" in denom:
                        self.balances["BTC"] = float(amount) / 100_000_000
                    elif "allETH" in denom:
                        self.balances["ETH"] = float(amount) / 1_000_000_000_000_000_000
                    elif "ibc/498A0751C798A0D9A389AA3691123DADA57DAA4FE165D5C75894505B876BA6E4" in denom:
                        self.balances["USDC"] = float(amount) / 1_000_000
                
                self.last_balance_update = time.time()
                
        except Exception as e:
            print(f"Error fetching balances: {e}")
            
        return self.balances

    def _parse_token_amount(self, token_string):
        """Parse a token string like '1000000uosmo' into amount and denom"""
        try:
            # Find the position where the numeric part ends
            for i, char in enumerate(token_string):
                if not (char.isdigit()):
                    amount = token_string[:i]
                    denom = token_string[i:]
                    return {'amount': int(amount), 'denom': denom}
                    
            # If we get here, the string was only digits
            return None
        except Exception as e:
            print(f"Error parsing token amount '{token_string}': {str(e)}")
            return None
    
    def _convert_to_human_readable(self, amount, denom):
        """Convert raw token amount to human-readable form based on denomination"""
        try:
            if denom == "uosmo":
                # OSMO has 6 decimals
                return amount / 1_000_000
            elif "allBTC" in denom:
                # BTC has 8 decimals
                return amount / 100_000_000
            elif "allETH" in denom or "factory/osmo1k6c8jln7ejuqwtqmay3yvzrg3kueaczl96pk067ldg8u835w0yhsw27twm/alloyed/allETH" in denom:
                # ETH has 18 decimals
                return amount / 1_000_000_000_000_000_000
            elif "ibc/498A0751C798A0D9A389AA3691123DADA57DAA4FE165D5C75894505B876BA6E4" in denom:
                # USDC has 6 decimals
                return amount / 1_000_000
            else:
                # Default to 6 decimals for unknown tokens
                return amount / 1_000_000
        except Exception as e:
            print(f"Error converting amount {amount} with denom {denom}: {str(e)}")
            return 0


    def get_pool_price(self, pair: str) -> dict:
        """Get the current price for a trading pair using poolmanager estimate-swap-exact-amount-in"""
        # Cache for successful price queries
        if not hasattr(self, 'price_cache'):
            self.price_cache = {}
        
        # Add cache cleanup to prevent memory growth
        if len(self.price_cache) > 15:  # Limit cache to 15 entries
            # Remove oldest entries
            oldest_pairs = sorted(self.price_cache.keys(), 
                                key=lambda k: self.price_cache[k]['timestamp'])[:5]
            for old_pair in oldest_pairs:
                del self.price_cache[old_pair]
        
        try:
            pool = self.pools.get(pair)
            if not pool:
                raise ValueError(f"Unsupported trading pair: {pair}")
                
            pool_id = pool["pool_id"]
            base_denom = pool["base_denom"]
            quote_denom = pool["quote_denom"]
            
            # Use small amounts for price queries to avoid slippage
            # Set appropriate test amounts based on token decimal places
            test_amount_base = None
            base_decimals = 6  # Default for most tokens
            
            if pair == "OSMO/USDC":
                test_amount_base = "1000000uosmo"  # 1 OSMO (6 decimals)
                base_decimals = 6
            elif pair == "BTC/USDC":
                test_amount_base = "100000factory/osmo1z6r6qdknhgsc0zeracktgpcxf43j6sekq07nw8sxduc9lg0qjjlqfu25e3/alloyed/allBTC"  # 0.001 BTC (8 decimals)
                base_decimals = 8
            elif pair == "ETH/USDC":
                test_amount_base = "1000000000000000factory/osmo1k6c8jln7ejuqwtqmay3yvzrg3kueaczl96pk067ldg8u835w0yhsw27twm/alloyed/allETH"  # 0.001 ETH (18 decimals)
                base_decimals = 18
            
            # USDC has 6 decimals
            test_amount_quote = "1000000ibc/498A0751C798A0D9A389AA3691123DADA57DAA4FE165D5C75894505B876BA6E4"  # 1 USDC
            quote_decimals = 6
            
            # Query price base -> quote using estimate-single-pool-swap-exact-amount-in
            base_to_quote_cmd = [
                "osmosisd", "query", "poolmanager", "estimate-single-pool-swap-exact-amount-in",
                pool_id, test_amount_base, quote_denom,
                "--output", "json"
            ]
            
            base_to_quote_result = subprocess.run(base_to_quote_cmd, capture_output=True, text=True)
            
            if base_to_quote_result.returncode != 0:
                # Check if this is the known spread factor error
                if "spread factor charge must be non-negative" in base_to_quote_result.stderr:
                    print(f"Using cached values for {pair} due to spread factor issue")
                    # Use cached price if available
                    if pair in self.price_cache:
                        print(f"Using cached price from {self.price_cache[pair]['timestamp']}")
                        return self.price_cache[pair]['data']
                    else:
                        raise ValueError(f"Failed to get base->quote price and no cache available")
                else:
                    print(f"Full stderr for {pair}: {base_to_quote_result.stderr}")
                    print(f"Full stdout for {pair}: {base_to_quote_result.stdout}")
                    raise ValueError(f"Failed to get base->quote price: {base_to_quote_result.stderr}")
                    
            base_to_quote_data = json.loads(base_to_quote_result.stdout)
            base_to_quote_amount = int(base_to_quote_data["token_out_amount"])
            
            # Query price quote -> base using estimate-single-pool-swap-exact-amount-in
            quote_to_base_cmd = [
                "osmosisd", "query", "poolmanager", "estimate-single-pool-swap-exact-amount-in",
                pool_id, test_amount_quote, base_denom,
                "--output", "json"
            ]
            
            quote_to_base_result = subprocess.run(quote_to_base_cmd, capture_output=True, text=True)
        
            if quote_to_base_result.returncode != 0:
                # Check if this is the known spread factor error
                if "spread factor charge must be non-negative" in quote_to_base_result.stderr:
                    print(f"Using cached values for {pair} due to spread factor issue")
                    # Use cached price if available
                    if pair in self.price_cache:
                        print(f"Using cached price from {self.price_cache[pair]['timestamp']}")
                        return self.price_cache[pair]['data']
                    else:
                        raise ValueError(f"Failed to get quote->base price and no cache available")
                else:
                    raise ValueError(f"Failed to get quote->base price: {quote_to_base_result.stderr}")
                    
            quote_to_base_data = json.loads(quote_to_base_result.stdout)
            quote_to_base_amount = int(quote_to_base_data["token_out_amount"])
        
            # Calculate prices with proper decimal handling
            base_amount_factor = 10**base_decimals  # Adjust based on token decimals
            if pair == "OSMO/USDC":
                base_amount = 1.0  # 1 OSMO
            else:
                base_amount = 0.001  # 0.001 BTC/ETH
                    
            quote_amount_factor = 10**quote_decimals  # 6 decimals for USDC
            quote_amount = 1.0  # 1 USDC
            
            # Calculate both price directions
            base_per_quote = (base_to_quote_amount / quote_amount_factor) / base_amount  # USDC per base token
            quote_per_base = (quote_to_base_amount / base_amount_factor) / quote_amount  # Base token per USDC
            
            price_data = {
                "base_per_quote": base_per_quote,  # e.g., USDC per BTC (number like 60000)
                "quote_per_base": quote_per_base,  # e.g., BTC per USDC (small number like 0.000016)
                "base_symbol": self._get_token_symbol(pool["base_denom"]),
                "quote_symbol": self._get_token_symbol(pool["quote_denom"]),
                "base_decimals": base_decimals,
                "quote_decimals": quote_decimals
            }
            
            # Cache the successful price
            self.price_cache[pair] = {
                'data': price_data,
                'timestamp': time.time()
            }
            
            return price_data
            
        except Exception as e:
            print(f"Error getting pool price: {e}")
            
            # Try to use cached price if available
            if hasattr(self, 'price_cache') and pair in self.price_cache:
                # Check if cache is not too old (e.g., less than 30 minutes)
                if time.time() - self.price_cache[pair]['timestamp'] < 1800:
                    print(f"Using cached price from {self.price_cache[pair]['timestamp']}")
                    return self.price_cache[pair]['data']
            
            # As a last resort, use hardcoded fallback values
            if pair == "BTC/USDC":
                return {
                    "base_per_quote": 65000.0,
                    "quote_per_base": 1/65000.0,
                    "base_symbol": "BTC", 
                    "quote_symbol": "USDC",
                    "base_decimals": 8,
                    "quote_decimals": 6
                }
            elif pair == "OSMO/USDC":
                return {
                    "base_per_quote": 0.80,
                    "quote_per_base": 1.25,
                    "base_symbol": "OSMO", 
                    "quote_symbol": "USDC",
                    "base_decimals": 6,
                    "quote_decimals": 6
                }
            elif pair == "ETH/USDC":
                return {
                    "base_per_quote": 3500.0,
                    "quote_per_base": 1/3500.0,
                    "base_symbol": "ETH", 
                    "quote_symbol": "USDC",
                    "base_decimals": 18,
                    "quote_decimals": 6
                }
            return {
                "base_per_quote": 0.0,
                "quote_per_base": 0.0,
                "base_symbol": "",
                "quote_symbol": "",
                "base_decimals": 6,
                "quote_decimals": 6
            }
    
    def _get_token_symbol(self, denom):
        """Get a human-readable symbol from a token denomination"""
        if denom == "uosmo":
            return "OSMO"
        elif "allBTC" in denom:
            return "BTC"
        elif "factory/osmo1k6c8jln7ejuqwtqmay3yvzrg3kueaczl96pk067ldg8u835w0yhsw27twm/alloyed/allETH" in denom:
            return "ETH"
        elif "498A0751C798A0D9A389AA3691123DADA57DAA4FE165D5C75894505B876BA6E4" in denom:
            return "USDC"
        return denom.split('/')[-1]

    def execute_market_swap(self, from_token_symbol, to_token_symbol, amount_in: float, min_out: float = None):
        """Execute a market swap with exact amount in"""
        try:
            # Find matching pool and denoms from symbols
            pair = None
            token_in = None
            token_out = None
        
            # Check each pool to find the right pair
            for pool_pair, pool_info in self.pools.items():
                base_symbol = self._get_token_symbol(pool_info["base_denom"])
                quote_symbol = self._get_token_symbol(pool_info["quote_denom"])
            
                if (from_token_symbol == base_symbol and to_token_symbol == quote_symbol):
                    pair = pool_pair
                    token_in = pool_info["base_denom"]
                    token_out = pool_info["quote_denom"]
                    break
                elif (from_token_symbol == quote_symbol and to_token_symbol == base_symbol):
                    pair = pool_pair
                    token_in = pool_info["quote_denom"]
                    token_out = pool_info["base_denom"]
                    break
            
            if not pair or not token_in or not token_out:
                raise ValueError(f"Could not find pool for {from_token_symbol} to {to_token_symbol}")
                
            pool = self.pools.get(pair)
            
            # Format the amount with proper denomination and decimals
            if "allBTC" in token_in:
                # allBTC uses 8 decimals
                amount_in_tokens = int(amount_in * 100000000)
            elif "factory/osmo1k6c8jln7ejuqwtqmay3yvzrg3kueaczl96pk067ldg8u835w0yhsw27twm/alloyed/allETH" in token_in:        
                # ETH uses 18 decimals
                amount_in_tokens = int(amount_in * 1000000000000000000)
            else:
                # Most tokens use 6 decimals on Osmosis
                amount_in_tokens = int(amount_in * 1000000)
                
            # Ensure no spaces between amount and denom - this is critical
            amount_in_formatted = f"{amount_in_tokens}{token_in}"
        
            # Set minimum output if provided
            min_amount_out = ""
            if min_out:
                if "allBTC" in token_out:
                    # allBTC uses 8 decimals
                    min_out_tokens = int(min_out * 100000000)
                else:
                    # Most tokens use 6 decimals
                    min_out_tokens = int(min_out * 1000000)
                    
                # Again, ensure no spaces between amount and denom
                min_amount_out = f"{min_out_tokens}"
            
            # Construct the command for a market swap with exact amount in
            cmd = [
                "osmosisd", "tx", "poolmanager", "swap-exact-amount-in",
                amount_in_formatted,
                min_amount_out,
                "--swap-route-pool-ids", pool["pool_id"],
                "--swap-route-denoms", token_out,
                "--from", self.wallet_name,
                "--chain-id", "osmosis-1",
                "--gas", "auto",
                "--gas-adjustment", "1.3",
                "--gas-prices", "0.035uosmo",
                "-y"
            ]
            
            # Execute the command
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"Error output: {result.stderr}")
                return {
                    "success": False,
                    "error": result.stderr
                }
            
            # Try to parse as JSON, but handle non-JSON responses
            try:
                response_data = json.loads(result.stdout)
                tx_hash = response_data.get("txhash", "Unknown")
                
                return {
                    "success": True,
                    "tx_hash": tx_hash
                }
            except json.JSONDecodeError:
                # Handle case where response is not valid JSON
                import re
                tx_hash_match = re.search(r'txhash:\s*([A-F0-9]+)', result.stdout)
                if tx_hash_match:
                    tx_hash = tx_hash_match.group(1)
                    return {
                        "success": True,
                        "tx_hash": tx_hash
                    }
                
                return {
                    "success": True,
                    "tx_hash": "Transaction submitted (hash not found in output)",
                    "raw_output": result.stdout
                }
                    
        except Exception as e:
            print(f"Exception during swap execution: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

class TransactionLogger:
    """Handles logging and retrieval of transaction history with enhanced details"""
    
    def __init__(self):
        self.transactions_file = "transactions.json"
        self.pending_orders_file = "pending_orders.json"
        
        # Create files if they don't exist
        if not os.path.exists(self.transactions_file):
            with open(self.transactions_file, 'w') as f:
                json.dump([], f)
                
        if not os.path.exists(self.pending_orders_file):
            with open(self.pending_orders_file, 'w') as f:
                json.dump([], f)
    
    def log_transaction(self, tx_data):
        """Log a completed transaction"""
        try:
            with open(self.transactions_file, 'r+') as f:
                transactions = json.load(f)
                transactions.append(tx_data)
                f.seek(0)
                json.dump(transactions, f, indent=2)
        except Exception as e:
            print(f"Error logging transaction: {e}")
    
    def update_transaction(self, tx_hash, updated_data):
        """Update an existing transaction with actual execution data"""
        try:
            with open(self.transactions_file, 'r+') as f:
                transactions = json.load(f)
                
                # Find the transaction by hash
                for tx in transactions:
                    if tx.get('tx_hash') == tx_hash:
                        tx.update(updated_data)
                        break
                
                # Write back the updated transactions
                f.seek(0)
                json.dump(transactions, f, indent=2)
                f.truncate()
                
            return True
        except Exception as e:
            print(f"Error updating transaction: {e}")
            return False
            
    def get_transactions(self):
        """Get all logged transactions"""
        try:
            with open(self.transactions_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading transactions: {e}")
            return []
    
    def add_pending_order(self, order_data):
        """Add a new pending limit order"""
        try:
            with open(self.pending_orders_file, 'r+') as f:
                orders = json.load(f)
                orders.append(order_data)
                f.seek(0)
                json.dump(orders, f, indent=2)
        except Exception as e:
            print(f"Error adding pending order: {e}")
    
    def get_pending_orders(self):
        """Get all pending limit orders"""
        try:
            with open(self.pending_orders_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading pending orders: {e}")
            return []
    
    def remove_pending_order(self, order_id):
        """Remove a completed or canceled order"""
        try:
            with open(self.pending_orders_file, 'r+') as f:
                orders = json.load(f)
                orders = [o for o in orders if o['id'] != order_id]
                f.seek(0)
                json.dump(orders, f, indent=2)
                f.truncate()
        except Exception as e:
            print(f"Error removing pending order: {e}")

class OsmosisTraderUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Osmosis Trader")
        self.root.geometry("600x500")
        
        # Initialize Osmosis client and transaction logger
        self.client = OsmosisClient(root)
        self.logger = TransactionLogger()

        self.price_cache_limit = 10  # Maximum price cache entries
        self.menu_cache_limit = 5    # Maximum menu cache entries
        self.price_cache_ttl = 300 

        self.order_id_counter = self._get_highest_order_id() + 1
        
        # Available tokens
        self.base_tokens = ["BTC", "ETH", "OSMO"]
        self.quote_token = "USDC"
        
        # Track if the user has manually set the min_out value
        self.min_out_manually_set = False
        
        # Track the last manual refresh time
        self.last_manual_refresh = time.time()
        
        # Current view state
        self.current_view = 'main'
        
        # Apply custom theme
        self._apply_osmosis_theme()
        
        self._create_ui()
        self._update_balance_display(initial_load=True)
        
        # Update price periodically
        self._start_price_updates()
        
        # Check pending orders periodically
        self._start_order_checker()

    def _apply_osmosis_theme(self):
        """Apply Osmosis theme colors to the UI"""
        style = ttk.Style()
        
        # Osmosis colors
        bg_color = "#151733"  # Dark blue background
        text_color = "#FFFFFF"  # White text
        accent_color = "#7c3aed"  # Purple accent
        secondary_color = "#0fabc9"  # Teal/cyan secondary color
        button_color = "#7c3aed"  # Button color
        
        # Configure the main window background
        self.root.configure(background=bg_color)
        
        # Configure styles for different widgets
        style.configure('TFrame', background=bg_color)
        style.configure('TLabel', background=bg_color, foreground=text_color)
        style.configure('TLabelframe', background=bg_color, foreground=text_color)
        style.configure('TLabelframe.Label', background=bg_color, foreground=text_color)
        
        # Configure entry style
        style.configure('TEntry', fieldbackground="#202442", foreground=text_color)
        
        # Configure button style
        style.configure('TButton', background=button_color, foreground=text_color)
        style.map('TButton', 
                 background=[('active', '#9965f4')],
                 foreground=[('active', text_color)])
        
        # Configure combobox style
        style.configure('TCombobox', 
                       fieldbackground="#202442", 
                       background=bg_color, 
                       foreground=text_color,
                       arrowcolor=text_color)
        
        # Configure checkbutton style
        style.configure('TCheckbutton', 
                       background=bg_color, 
                       foreground=text_color)
        
        # Create custom styles
        style.configure('Title.TLabel', 
                       background=bg_color, 
                       foreground="#a78bfa", 
                       font=("Helvetica", 18, "bold"))
        
        style.configure('Price.TLabel', 
                       background=bg_color, 
                       foreground=secondary_color, 
                       font=("Helvetica", 12))
        
        style.configure('Status.TLabel', 
                       background=bg_color, 
                       foreground="#E8EDDF", 
                       font=("Helvetica", 10))
        
        style.configure('Execute.TButton', 
                       background="#7c3aed", 
                       foreground=text_color,
                       font=("Helvetica", 11, "bold"))
        style.map('Execute.TButton', 
                 background=[('active', '#9965f4')],
                 foreground=[('active', text_color)])
                 
        style.configure('Success.TLabel', 
                       background=bg_color, 
                       foreground="#4ade80", 
                       font=("Helvetica", 10, "bold"))

        # Combobox styling
        style.map('TCombobox',
            fieldbackground=[('readonly', '#202442')],  # Dark blue-grey field
            selectbackground=[('readonly', '#7c3aed')],  # Purple selection
            selectforeground=[('readonly', 'white')],    # White text
            background=[('readonly', '#151733')]         # Dark blue background
        )
        
        # Combobox arrow color
        self.root.option_add('*TCombobox*Listbox*Background', '#202442')  # Dropdown bg
        self.root.option_add('*TCombobox*Listbox*Foreground', 'white')    # Dropdown text
        self.root.option_add('*TCombobox*Listbox*selectBackground', '#7c3aed')  # Selected item
        self.root.option_add('*TCombobox*Listbox*selectForeground', 'white')
        
        # Radiobutton styling
        style.configure('TRadiobutton', 
            background='#151733',       # Dark blue background
            foreground='white',         # White text
            selectcolor='#7c3aed',      # Purple selection dot (when selected)
            indicatorcolor='white',     # WHITE outer circle (when not selected)
            indicatorforeground='white', # White border
            font=('Helvetica', 10)
        )
        
        style.map('TRadiobutton',
            background=[('active', '#151733')],
            foreground=[('active', 'white')],
            indicatorcolor=[
                ('selected', '#7c3aed'),  # Purple when selected
                ('!selected', 'white')    # White when not selected
            ]
        )   

    def _create_ui(self):
        """Create the user interface with optimizations"""
        # Set application priority (Windows-specific)
        try:
            import ctypes
            process_handle = ctypes.windll.kernel32.GetCurrentProcess()
            ctypes.windll.kernel32.SetPriorityClass(process_handle, 0x00008000)  # ABOVE_NORMAL_PRIORITY_CLASS
        except:
            pass
        
        # Reduce Tkinter overhead
        self.root.tk.call('tk', 'scaling', 1.0)
        
        # Main frame
        self.main_frame = ttk.Frame(self.root, padding="20")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(self.main_frame, text="Osmosis Instant Swaps", style='Title.TLabel')
        title_label.pack(pady=(0, 20))
        
        # Form frame
        form_frame = ttk.LabelFrame(self.main_frame, text="Swap Details", padding="10")
        form_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        # Current price display
        price_frame = ttk.Frame(form_frame)
        price_frame.pack(fill=tk.X, pady=5)
        
        # Create a 2-column grid
        price_frame.columnconfigure(0, weight=1)
        price_frame.columnconfigure(1, weight=1)
        
        # Left column - Prices
        prices_column = ttk.Frame(price_frame)
        prices_column.grid(row=0, column=0, sticky="w")
        
        # Right column - Balances
        balances_column = ttk.Frame(price_frame)
        balances_column.grid(row=0, column=1, sticky="e", padx=20)
        
        # Prices display
        self.price_vars = {}
        for token in self.base_tokens:
            frame = ttk.Frame(prices_column)
            frame.pack(fill=tk.X, pady=2)
            ttk.Label(frame, text=f"{token} Price:").pack(side=tk.LEFT, padx=(0, 5))
            self.price_vars[token] = tk.StringVar(value="Loading...")
            ttk.Label(frame, textvariable=self.price_vars[token], style='Price.TLabel').pack(side=tk.LEFT)
        
        # Balances display (right column)
        ttk.Label(balances_column, text="Wallet Balances", style='Price.TLabel').pack(anchor=tk.E)
        
        self.balance_vars = {
            "BTC": tk.StringVar(value="BTC: -"),
            "ETH": tk.StringVar(value="ETH: -"), 
            "OSMO": tk.StringVar(value="OSMO: -"),
            "USDC": tk.StringVar(value="USDC: -"),
            "TOTAL": tk.StringVar(value="Total: $ -")
        }
        
        for token in ["BTC", "ETH", "OSMO", "USDC"]:
            ttk.Label(balances_column, 
                    textvariable=self.balance_vars[token],
                    style='Price.TLabel').pack(anchor=tk.E)
        
        ttk.Label(balances_column, 
                textvariable=self.balance_vars["TOTAL"],
                style='Price.TLabel',
                font=('Helvetica', 11, 'bold')).pack(anchor=tk.E, pady=(5,0))
            
        # Order type selection
        order_type_frame = ttk.Frame(form_frame)
        order_type_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(order_type_frame, text="Order Type:").pack(side=tk.LEFT, padx=(0, 5))
        self.order_type_var = tk.StringVar(value="market")
        ttk.Radiobutton(order_type_frame, text="Market", variable=self.order_type_var, value="market").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(order_type_frame, text="Limit", variable=self.order_type_var, value="limit").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(order_type_frame, text="Stop-Loss", variable=self.order_type_var, value="stop_loss").pack(side=tk.LEFT)
        
        # From/To Token Selection
        token_frame = ttk.Frame(form_frame)
        token_frame.pack(fill=tk.X, pady=10)
        
        # From Token (Sell)
        from_frame = ttk.LabelFrame(token_frame, text="From (Sell)")
        from_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        self.from_token_var = tk.StringVar(value=self.quote_token)
        tokens_for_from = self.base_tokens + [self.quote_token]
        self.from_token_menu = ttk.Combobox(from_frame, textvariable=self.from_token_var, 
                                           values=tokens_for_from, state="readonly", width=10)
        self.from_token_menu.pack(side=tk.TOP, pady=5, padx=5, fill=tk.X)
        self.from_token_menu.bind("<<ComboboxSelected>>", self._from_token_changed)
        
        self.amount_in_var = tk.StringVar()
        amount_in_entry = ttk.Entry(from_frame, textvariable=self.amount_in_var, width=15)
        amount_in_entry.pack(side=tk.TOP, pady=5, padx=5, fill=tk.X)
        
        # To Token (Buy)
        to_frame = ttk.LabelFrame(token_frame, text="To (Buy)")
        to_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.to_token_var = tk.StringVar(value=self.base_tokens[0])
        to_token_values = []
        self.to_token_menu = ttk.Combobox(to_frame, textvariable=self.to_token_var, 
                                         values=to_token_values, state="readonly", width=10)
        self.to_token_menu.pack(side=tk.TOP, pady=5, padx=5, fill=tk.X)
        self.to_token_menu.bind("<<ComboboxSelected>>", self._to_token_changed)
        
        # Create market order UI elements (modified)
        self.market_ui_frame = ttk.Frame(to_frame)  # Note: Don't pack yet
        self.min_out_var = tk.StringVar()
        self.min_out_entry = ttk.Entry(self.market_ui_frame, textvariable=self.min_out_var, width=15)
        self.min_out_entry.pack(side=tk.TOP, pady=5, padx=5, fill=tk.X)
        self.min_out_entry.bind("<KeyRelease>", self._min_out_changed)
        self.min_out_hint_var = tk.StringVar(value="(optional)")
        self.min_out_hint = ttk.Label(self.market_ui_frame, textvariable=self.min_out_hint_var, font=("Helvetica", 9))
        self.min_out_hint.pack(side=tk.TOP, padx=5, fill=tk.X)
        
        # Create limit order UI elements (modified)
        self.limit_ui_frame = ttk.Frame(to_frame)  # Note: Don't pack yet
        self.limit_price_frame = ttk.Frame(self.limit_ui_frame)
        self.limit_price_frame.pack(side=tk.TOP, pady=5, padx=5, fill=tk.X)
        ttk.Label(self.limit_price_frame, text="Limit Price:").pack(side=tk.LEFT, padx=(0, 5))
        self.limit_price_var = tk.StringVar()
        limit_price_entry = ttk.Entry(self.limit_price_frame, textvariable=self.limit_price_var, width=15)
        limit_price_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.limit_hint_var = tk.StringVar(value="(enter amount and price to see estimate)")
        self.limit_hint = ttk.Label(self.limit_ui_frame, textvariable=self.limit_hint_var, font=("Helvetica", 9))
        self.limit_hint.pack(side=tk.TOP, padx=5, fill=tk.X)

        self.stop_loss_ui_frame = ttk.Frame(to_frame)  # Note: Don't pack yet
        self.stop_price_frame = ttk.Frame(self.stop_loss_ui_frame)
        self.stop_price_frame.pack(side=tk.TOP, pady=5, padx=5, fill=tk.X)
        ttk.Label(self.stop_price_frame, text="Stop Price:").pack(side=tk.LEFT, padx=(0, 5))
        self.stop_price_var = tk.StringVar()
        stop_price_entry = ttk.Entry(self.stop_price_frame, textvariable=self.stop_price_var, width=15)
        stop_price_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.stop_loss_hint_var = tk.StringVar(value="(will sell when price falls below this level)")
        self.stop_loss_hint = ttk.Label(self.stop_loss_ui_frame, textvariable=self.stop_loss_hint_var, font=("Helvetica", 9))
        self.stop_loss_hint.pack(side=tk.TOP, padx=5, fill=tk.X)
        
        # Create slippage settings frame (modified)
        self.slippage_frame = ttk.Frame(form_frame)  # Note: Don't pack yet
        ttk.Label(self.slippage_frame, text="Slippage Tolerance:").pack(side=tk.LEFT, padx=(0, 5))
        self.slippage_var = tk.StringVar(value="0.5")  # Default to 0.5%
        slippage_combo = ttk.Combobox(self.slippage_frame, textvariable=self.slippage_var, 
                                      values=["0.1", "0.5", "1.0", "2.0", "3.0", "5.0"], width=5)
        slippage_combo.pack(side=tk.LEFT)
        ttk.Label(self.slippage_frame, text="%").pack(side=tk.LEFT)

        self._update_order_type_ui() 
        


        
        # Flip tokens button
        flip_button = ttk.Button(form_frame, text="↔ Flip", command=self._flip_tokens, width=10)
        flip_button.pack(pady=5)
        
        # Bind order type change to update UI
        self.order_type_var.trace_add("write", lambda *args: self._update_order_type_ui())
        
        # Buttons frame at the bottom
        button_frame = ttk.Frame(self.main_frame)
        button_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        # Status frame above buttons
        status_frame = ttk.Frame(self.main_frame)
        status_frame.pack(fill=tk.X, pady=(0, 10), side=tk.BOTTOM)
        
        # Status and notifications
        self.status_var = tk.StringVar()
        status_label = ttk.Label(status_frame, textvariable=self.status_var, wraplength=550, style='Status.TLabel')
        status_label.pack(fill=tk.X)
        
        # Add a special refresh notification
        self.refresh_notify_var = tk.StringVar()
        refresh_notify_label = ttk.Label(status_frame, textvariable=self.refresh_notify_var, style='Success.TLabel')
        refresh_notify_label.pack(fill=tk.X, pady=(5, 0))
        
        # Buttons
        execute_button = ttk.Button(button_frame, text="Execute Order", command=self._execute_order, style='Execute.TButton')
        execute_button.pack(side=tk.LEFT, padx=(0, 10))
        
        refresh_button = ttk.Button(button_frame, text="Refresh Price", command=self._manual_refresh)
        refresh_button.pack(side=tk.LEFT)
        
        # Transactions and Pending Orders buttons
        transactions_button = ttk.Button(button_frame, text="View Transactions", command=self._show_transactions)
        transactions_button.pack(side=tk.RIGHT, padx=(0, 10))
        
        pending_orders_button = ttk.Button(button_frame, text="Pending Orders", command=self._show_pending_orders)
        pending_orders_button.pack(side=tk.RIGHT)
        
        
        # Initialize typing timers
        self.amount_in_typing_timer = None
        self.limit_price_typing_timer = None

        # Set up optimized trace callbacks with typing delays
        self.amount_in_var.trace_add("write", self._debounce_amount_update)
        self.limit_price_var.trace_add("write", self._debounce_limit_price_update)
        self.from_token_var.trace_add("write", lambda *args: self._update_min_out_hint_if_auto())
        self.to_token_var.trace_add("write", lambda *args: self._update_min_out_hint_if_auto())
        
        # Initial setup of token dropdown values
        self._update_to_token_menu()
        
        # Update UI based on order type
        self._update_order_type_ui()
        
        # Schedule the initial price update
        self.root.after(100, self._update_all_prices)

    def _cleanup_caches(self):
       """Remove old cache entries to prevent memory bloat"""
       current_time = time.time()
       
       # Clean price info cache
       if hasattr(self, '_price_info_cache'):
           # Remove expired entries first
           expired_keys = [k for k, v in self._price_info_cache.items() 
                          if current_time - v['timestamp'] > self.price_cache_ttl]
           for key in expired_keys:
               del self._price_info_cache[key]
               
           # If still too many entries, remove oldest ones
           if len(self._price_info_cache) > self.price_cache_limit:
               sorted_keys = sorted(self._price_info_cache.keys(), 
                                   key=lambda k: self._price_info_cache[k]['timestamp'])
               for key in sorted_keys[:len(sorted_keys) - self.price_cache_limit]:
                   del self._price_info_cache[key]
       
       # Clean menu cache
       if hasattr(self, '_menu_cache'):
           # Remove expired entries
           expired_keys = [k for k, v in self._menu_cache.items() 
                          if current_time - v['timestamp'] > self.price_cache_ttl]
           for key in expired_keys:
               del self._menu_cache[key]
               
           # If still too many entries, remove oldest ones
           if len(self._menu_cache) > self.menu_cache_limit:
               sorted_keys = sorted(self._menu_cache.keys(), 
                                   key=lambda k: self._menu_cache[k]['timestamp'])
               for key in sorted_keys[:len(sorted_keys) - self.menu_cache_limit]:
                   del self._menu_cache[key]    
           
    def _update_order_type_ui(self):
        """Update the UI based on the selected order type without recreating widgets"""
        order_type = self.order_type_var.get()
    
        # Don't redraw if the UI state hasn't changed
        if hasattr(self, '_last_order_type') and self._last_order_type == order_type:
            return
        self._last_order_type = order_type

        # Cancel any pending updates
        if hasattr(self, '_limit_update_job'):
            self.root.after_cancel(self._limit_update_job)
    
        # Simply show/hide frames instead of recreating them
        if order_type == "market":
            self.limit_ui_frame.pack_forget()
            self.stop_loss_ui_frame.pack_forget()
            self.market_ui_frame.pack(in_=self.to_token_menu.master, side=tk.TOP, fill=tk.X, pady=5)
            self.slippage_frame.pack(fill=tk.X, pady=5)
            self.min_out_hint_var.set("(optional)")
            self.min_out_manually_set = False
        elif order_type == "limit":
            self.market_ui_frame.pack_forget()
            self.stop_loss_ui_frame.pack_forget()
            self.slippage_frame.pack_forget()
            self.limit_ui_frame.pack(in_=self.to_token_menu.master, side=tk.TOP, fill=tk.X)
            self.limit_hint_var.set("(enter amount and price to see estimate)")
        else:  # stop_loss
            self.market_ui_frame.pack_forget()
            self.limit_ui_frame.pack_forget()
            self.slippage_frame.pack_forget()
            self.stop_loss_ui_frame.pack(in_=self.to_token_menu.master, side=tk.TOP, fill=tk.X)
            self.stop_loss_hint_var.set("(will sell when price falls below this level)")
    
        # Update the display
        self._defer_hint_update()
                
    def _show_pending_orders(self):
        """Show the pending orders view"""
        if self.current_view == 'pending_orders':
            return
            
        # Hide main frame
        self.main_frame.pack_forget()
        
        # Create pending orders frame if it doesn't exist
        if not hasattr(self, 'pending_orders_frame'):
            self._create_pending_orders_view()
        
        # Show pending orders frame
        self.pending_orders_frame.pack(fill=tk.BOTH, expand=True)
        self.current_view = 'pending_orders'
        
        # Update pending orders list
        self._update_pending_orders_list()
    
    def _create_pending_orders_view(self):
        """Create the pending orders view"""
        self.pending_orders_frame = ttk.Frame(self.root, padding="20")
        
        # Title and back button
        title_frame = ttk.Frame(self.pending_orders_frame)
        title_frame.pack(fill=tk.X, pady=(0, 20))
        
        back_button = ttk.Button(title_frame, text="← Back", command=self._show_main_view)
        back_button.pack(side=tk.LEFT)
        
        title_label = ttk.Label(title_frame, text="Pending Limit Orders", style='Title.TLabel')
        title_label.pack(side=tk.LEFT, padx=10)
        
        # Pending orders list
        list_frame = ttk.Frame(self.pending_orders_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create a Treeview widget with scrollbars
        tree_scroll = ttk.Scrollbar(list_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.pending_orders_tree = ttk.Treeview(
            list_frame,
            yscrollcommand=tree_scroll.set,
            selectmode="extended",
            columns=("id", "created", "type", "pair", "amount", "price", "action"),
            show="headings"
        )
        self.pending_orders_tree.pack(fill=tk.BOTH, expand=True)
        
        tree_scroll.config(command=self.pending_orders_tree.yview)
        
        # Define columns
        self.pending_orders_tree.heading("id", text="ID", anchor=tk.W)
        self.pending_orders_tree.heading("created", text="Created", anchor=tk.W)
        self.pending_orders_tree.heading("type", text="Type", anchor=tk.W)
        self.pending_orders_tree.heading("pair", text="Pair", anchor=tk.W)
        self.pending_orders_tree.heading("amount", text="Amount", anchor=tk.W)
        self.pending_orders_tree.heading("price", text="Price", anchor=tk.W)
        self.pending_orders_tree.heading("action", text="Action", anchor=tk.W)
        
        # Configure column widths
        self.pending_orders_tree.column("id", width=80, stretch=tk.NO)
        self.pending_orders_tree.column("created", width=120, stretch=tk.NO)
        self.pending_orders_tree.column("type", width=80, stretch=tk.NO)
        self.pending_orders_tree.column("pair", width=100, stretch=tk.NO)
        self.pending_orders_tree.column("amount", width=100, stretch=tk.NO)
        self.pending_orders_tree.column("price", width=100, stretch=tk.NO)
        self.pending_orders_tree.column("action", width=100, stretch=tk.NO)
        
        # Add a frame for buttons at the bottom
        button_frame = ttk.Frame(self.pending_orders_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        # Refresh button
        refresh_button = ttk.Button(
            button_frame,
            text="Refresh",
            command=self._update_pending_orders_list
        )
        refresh_button.pack(side=tk.LEFT)
        
        # Cancel selected button
        cancel_button = ttk.Button(
            button_frame,
            text="Cancel Selected",
            command=self._cancel_selected_orders
        )
        cancel_button.pack(side=tk.RIGHT)
    
    def _update_pending_orders_list(self):
        """Update the pending orders list with current data"""
        # Clear existing items
        for item in self.pending_orders_tree.get_children():
            self.pending_orders_tree.delete(item)
        
        # Get pending orders from logger
        pending_orders = self.logger.get_pending_orders()
        
        # Add pending orders to the treeview
        for order in pending_orders:
            # Format timestamp
            created = datetime.fromisoformat(order['timestamp']).strftime("%Y-%m-%d %H:%M")
            
            # Determine pair
            pair = f"{order['from_token']}/{order['to_token']}"
            
            # Format price based on order type
            if order['order_type'] == 'stop_loss':
                price_value = order.get('stop_price', 0)
                price_display = f"{price_value:.6f} (stop)"
            else:  # limit orders
                price_value = order.get('limit_price', 0)
                price_display = f"{price_value:.6f}"
            
            # Add to treeview
            self.pending_orders_tree.insert("", tk.END, values=(
                order['id'],
                created,
                order['order_type'].replace('_', ' ').title(),
                pair,
                f"{order['amount']:.6f}",
                price_display,
                "Cancel"
            ))
        
    def _cancel_selected_orders(self):
        """Cancel the selected pending orders"""
        selected_items = self.pending_orders_tree.selection()
        if not selected_items:
            self.status_var.set("No orders selected for cancellation")
            return
            
        for item in selected_items:
            order_id = self.pending_orders_tree.item(item, 'values')[0]
            self.logger.remove_pending_order(order_id)
        
        self._update_pending_orders_list()
        self.status_var.set(f"Cancelled {len(selected_items)} order(s)")

    def _get_highest_order_id(self):
        """Find the highest order ID from both completed transactions and pending orders"""
        highest_id = 0
    
        # Check completed transactions
        for tx in self.logger.get_transactions():
            # Some older transactions might not have an ID field
            if 'order_id' in tx:
                try:
                    # Extract numeric part of order ID
                    order_num = int(tx['order_id'].split('-')[1])
                    highest_id = max(highest_id, order_num)
                except (IndexError, ValueError):
                    pass
            # Also check tx_hash field which might contain the old order ID format
            elif 'tx_hash' in tx and tx['tx_hash'].startswith('order-'):
                try:
                    order_num = int(tx['tx_hash'].split('-')[1])
                    highest_id = max(highest_id, order_num)
                except (IndexError, ValueError):
                    pass
        
        # Check pending orders
        for order in self.logger.get_pending_orders():
            try:
                # Extract numeric part of order ID
                order_num = int(order['id'].split('-')[1])
                highest_id = max(highest_id, order_num)
            except (IndexError, ValueError):
                pass

        return highest_id

    def _show_main_view(self):
        """Return to the main trading view"""
        if self.current_view == 'main':
            return
            
        # Hide current frame
        if self.current_view == 'transactions':
            self.transactions_frame.pack_forget()
        elif self.current_view == 'pending_orders':
            self.pending_orders_frame.pack_forget()
        
        # Show main frame
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.current_view = 'main'
    
    def _update_limit_price_hint(self):
        """Update the hint for limit price based ONLY on user inputs - no price queries"""
        # Get user inputs
        amount_str = self.amount_in_var.get().strip()
        limit_price_str = self.limit_price_var.get().strip()
        from_token = self.from_token_var.get()
        to_token = self.to_token_var.get()
        
        # Early returns for incomplete inputs
        if not amount_str or not limit_price_str:
            self.limit_hint_var.set("Enter amount and price to see estimate")
            return
        
        # Return for invalid token combinations
        if from_token == to_token:
            self.limit_hint_var.set("Cannot swap same token")
            return
        
        try:
            # Parse user inputs
            amount = float(amount_str)
            limit_price = float(limit_price_str)
            
            # Calculate expected output based on direction without any price query
            if from_token in self.base_tokens and to_token == self.quote_token:
                # Sell limit (base -> quote)
                expected_out = amount * limit_price
                price_text = f"Will receive: {expected_out:.6f} {to_token} at {limit_price:.6f}"
                self.min_out_var.set(f"{expected_out:.6f}")
            elif from_token == self.quote_token and to_token in self.base_tokens:
                # Buy limit (quote -> base)
                expected_out = amount / limit_price
                price_text = f"Will receive: {expected_out:.8f} {to_token} at {limit_price:.6f}"
                self.min_out_var.set(f"{expected_out:.8f}")
            else:
                self.limit_hint_var.set("Invalid token pair")
                return
            
            self.limit_hint_var.set(price_text)
        
        except ValueError:
            self.limit_hint_var.set("Invalid input values")
        except Exception as e:
            self.limit_hint_var.set("Calculation error")
            print(f"Error updating limit price hint: {e}")

    def _defer_hint_update(self):
        """Deferred hint update with minimal price queries"""
        if self.order_type_var.get() == "market":
            # Only market orders need current prices
            self._update_hint_only()
        else:
            # Limit orders only need price data from user inputs
            self._update_limit_price_hint()

    def _from_token_changed(self, event=None):
        """Handle from token selection change without redundant price queries"""
        from_token = self.from_token_var.get()
        
        # Check if the selection actually changed
        if hasattr(self, '_last_from_token') and self._last_from_token == from_token:
            return
        self._last_from_token = from_token
        
        # Update the "to" token dropdown based on from token
        self._update_to_token_menu()
        
        # Clear input fields
        self.amount_in_var.set("")
        self.min_out_var.set("")
        self.min_out_manually_set = False
        self.limit_price_var.set("")
        
        # For limit orders, just reset the hint without price queries
        if self.order_type_var.get() == "limit":
            self.limit_hint_var.set("Enter amount and price to see estimate")
        else:
            # Only do price queries for market orders
            self.root.after(100, self._update_hint_only)

    def _to_token_changed(self, event=None):
        """Handle to token selection change"""
        # Clear min_out field and update hint
        self.min_out_var.set("")
        self.min_out_manually_set = False
        self.limit_price_var.set("")
        
        # Update hint based on order type
        if self.order_type_var.get() == "market":
            self._update_hint_only()
        else:
            self._update_limit_price_hint()

    def _update_to_token_menu(self):
        """Update the 'to token' dropdown based on the selected 'from token' with caching"""
        from_token = self.from_token_var.get()
    
        # Use cached values if available
        cache_key = f"to_menu_{from_token}"
        if hasattr(self, '_menu_cache') and cache_key in self._menu_cache:
            to_token_values = self._menu_cache[cache_key]['values']
            default_token = self._menu_cache[cache_key]['default']
        else:
            # Generate new values
            if from_token == self.quote_token:  # If from is USDC
                to_token_values = self.base_tokens
            else:  # If from is a base token
                to_token_values = [self.quote_token]
            default_token = to_token_values[0]
        
            # Cache the result
            if not hasattr(self, '_menu_cache'):
                self._menu_cache = {}
            self._menu_cache[cache_key] = {
                'values': to_token_values,
                'default': default_token,
                'timestamp': time.time()
            }
        
        # Only update if values changed
        current_values = list(self.to_token_menu['values'])
        if current_values != to_token_values:
            self.to_token_menu['values'] = to_token_values
            
            # Set default value if current selection is invalid
            if self.to_token_var.get() not in to_token_values:
                self.to_token_var.set(default_token)
        
    def _update_balance_display(self, initial_load=False):
        """Update the balance display with current values"""
        # Force update on first load, otherwise use caching
        balances = self.client.get_wallet_balances(force_update=initial_load)
        
        prices = {
            "BTC": self._get_current_price("BTC"),
            "ETH": self._get_current_price("ETH"), 
            "OSMO": self._get_current_price("OSMO"),
            "USDC": 1.0
        }
        
        total_value = 0
        
        for token, amount in balances.items():
            self.balance_vars[token].set(
                f"{token}: {amount:.6f}" if token in ["BTC", "ETH"] else f"{token}: {amount:.2f}"
            )
            total_value += amount * prices.get(token, 0)
        
        self.balance_vars["TOTAL"].set(f"Total: ${total_value:,.2f}")
    
    def _get_current_price(self, token):
        """Get current price of a token in USDC"""
        if token == "USDC":
            return 1.0
            
        pair = f"{token}/USDC"
        price_info = self.client.get_pool_price(pair)
        return price_info['base_per_quote']

    def _update_all_prices(self):
        """Update all token prices display with minimal UI updates"""
        try:
            updated = False
        
            # Get and update the price for each base token
            for base_token in self.base_tokens:
                pair = f"{base_token}/{self.quote_token}"
                price_info = self.client.get_pool_price(pair)
                
                # Only update if price changed
                new_price_text = f"1 {base_token} = {price_info['base_per_quote']:.4f} {self.quote_token}"
                if self.price_vars[base_token].get() != new_price_text:
                    self.price_vars[base_token].set(new_price_text)
                    updated = True
            
            if updated:
                self.status_var.set("")
                # Only update balance display occasionally (no need for constant updates)
                if not hasattr(self, '_last_balance_update') or time.time() - self._last_balance_update > 30:
                    self._update_balance_display()
                    self._last_balance_update = time.time()
                
                # Update limit price hint if needed and visible
                if self.order_type_var.get() == "limit" and self.limit_ui_frame.winfo_ismapped():
                    self._update_limit_price_hint()
        
        except Exception as e:
            self.status_var.set(f"Error updating prices: {str(e)}")
            print(f"Error updating prices: {e}")

    def _debounce_amount_update(self, *args):
        """Delay updates while typing amount"""
        if self.amount_in_typing_timer:
            self.root.after_cancel(self.amount_in_typing_timer)
        
        # Wait for 300ms after last keystroke before updating
        self.amount_in_typing_timer = self.root.after(300, self._update_min_out_hint_if_auto)
    
    def _debounce_limit_price_update(self, *args):
        """Improved debouncing for limit price updates"""
        # Cancel any existing timer
        if self.limit_price_typing_timer:
            self.root.after_cancel(self.limit_price_typing_timer)
        
        # Increase debounce time for better performance
        self.limit_price_typing_timer = self.root.after(500, self._update_limit_price_hint)

    def _min_out_changed(self, event):
        """Track when user manually changes the min_out field"""
        self.min_out_manually_set = True

    def _update_min_out_hint_if_auto(self):
        """Only update min out hint if user hasn't manually set it"""
        # Don't run if fields are empty
        if not self.amount_in_var.get().strip():
            return
            
        if self.order_type_var.get() == "market":
            if not self.min_out_manually_set:
                self._update_min_out_hint()
            else:
                # Just update the hint text without changing the value
                self._update_hint_only()
        else:
            self._update_limit_price_hint()
    
    def _get_price_info_for_tokens(self):
        """Get price info for the current token pair with caching"""
        from_token = self.from_token_var.get()
        to_token = self.to_token_var.get()
        
        # Use a short cache to avoid repeated calculations
        cache_key = f"{from_token}_{to_token}"
        current_time = time.time()
        
        if hasattr(self, '_price_info_cache') and cache_key in self._price_info_cache:
            cache_entry = self._price_info_cache[cache_key]
            if current_time - cache_entry['timestamp'] < 0.25:  # 250ms cache
                return cache_entry['data'], cache_entry['is_reversed']
        
        # Determine the correct pair format to query
        if from_token in self.base_tokens and to_token == self.quote_token:
            # Selling base for quote (e.g., BTC/USDC)
            pair = f"{from_token}/{to_token}"
            is_reversed = False
        elif from_token == self.quote_token and to_token in self.base_tokens:
            # Selling quote for base (e.g., USDC/BTC)
            pair = f"{to_token}/{from_token}"
            is_reversed = True
        else:
            # This shouldn't happen with the simplified UI
            raise ValueError(f"Invalid token pair: {from_token}/{to_token}")
        
        # Get price info
        price_info = self.client.get_pool_price(pair)
        
        # Cache the result
        if not hasattr(self, '_price_info_cache'):
            self._price_info_cache = {}
        self._price_info_cache[cache_key] = {
            'data': price_info,
            'is_reversed': is_reversed,
            'timestamp': current_time
        }
    
        return price_info, is_reversed
        
    def _update_hint_only(self):
        """Update just the hint text without changing the min_out value"""
        # Skip calculations if amount field is empty
        amount_str = self.amount_in_var.get().strip()
        if not amount_str:
            self.min_out_hint_var.set("(optional)")
            return
            
        try:
            # First try to use cached price if recent (within 30 seconds)
            from_token = self.from_token_var.get()
            to_token = self.to_token_var.get()
            cache_key = f"{from_token}_{to_token}"
            current_time = time.time()
            
            if hasattr(self, '_price_info_cache') and cache_key in self._price_info_cache:
                cache_entry = self._price_info_cache[cache_key]
                if current_time - cache_entry['timestamp'] < 30:  # Use cache if <30s old
                    price_info = cache_entry['data']
                    is_reversed = cache_entry['is_reversed']
                    use_cached = True
                else:
                    use_cached = False
            else:
                use_cached = False
            
            if not use_cached:
                try:
                    price_info, is_reversed = self._get_price_info_for_tokens()
                except ValueError as e:
                    self.min_out_hint_var.set(str(e))
                    return
                    
            try:
                amount = float(amount_str)
            except ValueError:
                self.min_out_hint_var.set("Invalid amount")
                return
                
            if amount <= 0:
                self.min_out_hint_var.set("Amount must be positive")
                return
                
            # Get from/to tokens
            from_token = self.from_token_var.get()
            to_token = self.to_token_var.get()
            
            # Calculate expected output based on direction
            if not is_reversed:
                # Selling base for quote (e.g., selling BTC for USDC)
                expected_out = amount * price_info['base_per_quote']
            else:
                # Selling quote for base (e.g., selling USDC for BTC)
                expected_out = amount * price_info['quote_per_base']
            
            # Show estimated output without updating the min_out field
            if to_token == "BTC":
                self.min_out_hint_var.set(f"Est. output: {expected_out:.8f} {to_token}")
            else:
                self.min_out_hint_var.set(f"Est. output: {expected_out:.6f} {to_token}")
            
        except Exception as e:
            self.min_out_hint_var.set("Calculation error")
            print(f"Error calculating hint: {e}")
    
    def _update_min_out_hint(self):
        try:
            # Get from/to tokens
            from_token = self.from_token_var.get()
            to_token = self.to_token_var.get()
            amount_str = self.amount_in_var.get().strip()
            
            # Get amount
            try:
                amount = float(amount_str)
                if amount <= 0:
                    raise ValueError("Amount must be positive")
            except ValueError:
                self.min_out_hint_var.set("Invalid amount")
                return
        
            if self.order_type_var.get() == "market":
                # MARKET ORDER - use current price with slippage
                try:
                    # Use cached price with force_query=False
                    price_info, is_reversed = self._get_price_info_for_tokens(force_query=False)
                    
                    slippage_pct = float(self.slippage_var.get())
                    if slippage_pct <= 0:
                        raise ValueError("Slippage must be positive")
                    
                    # Calculate expected output
                    if not is_reversed:
                        expected_out = amount * price_info['base_per_quote']
                    else:
                        expected_out = amount * price_info['quote_per_base']
                    
                    min_out = expected_out * (1 - slippage_pct/100)
                    hint_text = f"Est. output: {expected_out:.8f} {to_token}" if to_token == "BTC" else f"Est. output: {expected_out:.6f} {to_token}"
                    hint_text += f" (with {slippage_pct}% slippage)"
                    
                    # Update the output field (only if not manually set)
                    if not self.min_out_manually_set:
                        self.min_out_var.set(f"{min_out:.8f}" if to_token == "BTC" else f"{min_out:.6f}")
                    
                    self.min_out_hint_var.set(hint_text)
                    
                except Exception as e:
                    self.min_out_hint_var.set(f"Error: {str(e)}")
                    print(f"Error calculating min out: {e}")
            
        except Exception as e:
            self.min_out_hint_var.set("Calculation error")
            print(f"Error calculating min out: {e}")
                   
    def _flip_tokens(self):
        """Swap the from and to tokens"""
        from_token = self.from_token_var.get()
        to_token = self.to_token_var.get()
        
        # Set the new values
        self.from_token_var.set(to_token)
        
        # Update the "to" token menu
        self._update_to_token_menu()
        
        # Try to set the original "from" token as "to"
        if from_token in self.to_token_menu['values']:
            self.to_token_var.set(from_token)
        
        # Clear amounts to avoid confusion
        self.amount_in_var.set("")
        self.min_out_var.set("")
        self.min_out_manually_set = False
        self.limit_price_var.set("")
        
        # Update hint based on order type
        if self.order_type_var.get() == "market":
            self._update_min_out_hint_if_auto()
        else:
            self._update_limit_price_hint()
    
    def _manual_refresh(self):
        """Manually refresh price and update expected output"""
        # Update the display with fresh price data
        self._update_all_prices()
        
        # Force update of the expected output amount, even if manually set
        temp_manual_state = self.min_out_manually_set
        self.min_out_manually_set = False
        
        # Update min out with latest price info and reset flag state
        if self.order_type_var.get() == "market":
            self._update_min_out_hint()
        else:
            self._update_limit_price_hint()
        
        # If it was previously manually set, consider the new value manually set too
        self.min_out_manually_set = temp_manual_state
        
        # Record the time of manual refresh
        self.last_manual_refresh = time.time()
        
        # Provide feedback to user
        self.refresh_notify_var.set("✓ Price refreshed & output updated!")
        self.root.after(2000, lambda: self.refresh_notify_var.set(""))

    def _start_price_updates(self):
        """Start periodic price updates"""
        def update_price_thread():
            cleanup_counter = 0  # Add counter for periodic cleanup
            
            while True:
                try:
                    # Update all prices
                    self.root.after(0, self._update_all_prices)
                    
                    # Check if it's been more than 1 minute since the last manual refresh
                    # and update the expected output automatically if needed
                    current_time = time.time()
                    if current_time - self.last_manual_refresh > 60:  # 60 seconds = 1 minute
                        self.root.after(0, self._auto_update_expected_output)
                    
                    # Perform memory cleanup every 5 price updates (2.5 minutes at 30-second intervals)
                    cleanup_counter += 1
                    if cleanup_counter >= 5:
                        self.root.after(0, self._cleanup_caches)
                        cleanup_counter = 0
                        
                except Exception as e:
                    print(f"Error in price update thread: {e}")
                    
                time.sleep(30)  # Update every 30 seconds
                    
        # Start the update thread
        thread = threading.Thread(target=update_price_thread, daemon=True)
        thread.start()
        
    def _start_order_checker(self):
        """Start periodic checking of pending limit orders"""
        def check_orders_thread():
            while True:
                try:
                    # Check pending orders every 10 seconds for more responsiveness
                    time.sleep(10)
                    self.root.after(0, self._check_pending_orders)
                except Exception as e:
                    print(f"Error in order checker thread: {e}")
                    
        # Start the order checker thread
        thread = threading.Thread(target=check_orders_thread, daemon=True)
        thread.start()
    
    def _check_pending_orders(self):
        """Check pending orders for all supported trading pairs and order types"""
        try:
            pending_orders = self.logger.get_pending_orders()
            if not pending_orders:
                return
                    
            executed_orders = []
            
            for order in pending_orders:
                try:
                    # Initialize result to None for each order
                    result = None
                    
                    # -- LIMIT ORDERS --
                    if order['order_type'] in ["sell_limit", "buy_limit"]:
                        # Determine the correct trading pair format
                        if order['from_token'] in self.base_tokens and order['to_token'] == self.quote_token:
                            # Selling base token for USDC (e.g., BTC->USDC, OSMO->USDC)
                            pair = f"{order['from_token']}/{order['to_token']}"
                            price_info = self.client.get_pool_price(pair)
                            current_price = price_info['base_per_quote']  # USDC per token
                            
                            # Sell limit: execute if current price >= limit price
                            if order['order_type'] == "sell_limit" and current_price >= order['limit_price']:
                                amount_out_expected = order['amount'] * current_price
                                result = self.client.execute_market_swap(
                                    order['from_token'],
                                    order['to_token'],
                                    order['amount'],
                                    amount_out_expected * 0.997  # 0.3% slippage
                                )
                        
                        elif order['from_token'] == self.quote_token and order['to_token'] in self.base_tokens:
                            # Buying base token with USDC (e.g., USDC->BTC, USDC->OSMO)
                            pair = f"{order['to_token']}/{order['from_token']}"  # BTC/USDC format
                            price_info = self.client.get_pool_price(pair)
                            current_price = price_info['base_per_quote']  # USDC per token
                            
                            # Buy limit: execute if current price <= limit price
                            if order['order_type'] == "buy_limit" and current_price <= order['limit_price']:
                                amount_out_expected = order['amount'] / current_price
                                result = self.client.execute_market_swap(
                                    order['from_token'],
                                    order['to_token'],
                                    order['amount'],
                                    amount_out_expected * 0.997  # 0.3% slippage
                                )
                    
                    # -- STOP-LOSS ORDERS --
                    elif order['order_type'] == "stop_loss":
                        # Stop-loss orders should always be selling base tokens for quote tokens
                        if order['from_token'] in self.base_tokens and order['to_token'] == self.quote_token:
                            pair = f"{order['from_token']}/{order['to_token']}"
                            price_info = self.client.get_pool_price(pair)
                            current_price = price_info['base_per_quote']  # USDC per token
                            
                            # Execute if current price <= stop price (price has fallen below threshold)
                            if current_price <= order['stop_price']:
                                # Calculate expected output with current price
                                amount_out_expected = order['amount'] * current_price
                                
                                # Execute the market swap
                                result = self.client.execute_market_swap(
                                    order['from_token'],
                                    order['to_token'],
                                    order['amount'],
                                    amount_out_expected * 0.997  # 0.3% slippage for market execution
                                )
                    
                    # Process result if the order was executed
                    if result and result['success']:
                        # Calculate expected values based on order type
                        if order['order_type'] == 'sell_limit':
                            expected_price = order['limit_price']
                            expected_out = order['amount'] * expected_price
                        elif order['order_type'] == 'buy_limit':
                            expected_price = order['limit_price']
                            expected_out = order['amount'] / expected_price
                        elif order['order_type'] == 'stop_loss':
                            expected_price = current_price
                            expected_out = order['amount'] * current_price
                        else:
                            expected_price = None
                            expected_out = None
                        
                        # Build transaction data object with expected values
                        tx_data = {
                            'timestamp': datetime.now().isoformat(),
                            'tx_hash': result['tx_hash'],
                            'order_id': order['id'],
                            'from_token': order['from_token'],
                            'to_token': order['to_token'],
                            'amount_in': order['amount'],
                            'expected_amount_out': expected_out,
                            'actual_amount_out': None,  # Will be updated after query
                            'execution_price': None,    # Will be updated after query
                            'order_type': order['order_type'],
                            'status': 'executed'
                        }
                        
                        # Add order-specific price fields
                        if order['order_type'] == 'stop_loss':
                            tx_data['stop_price'] = order['stop_price']
                        else:  # limit orders
                            tx_data['limit_price'] = order['limit_price']
                        
                        # Log the transaction
                        self.logger.log_transaction(tx_data)
                        executed_orders.append(order['id'])
                        
                        # Query actual transaction data in background
                        self._query_actual_transaction(result['tx_hash'])
                        
                        # Notification based on order type
                        if order['order_type'] == 'stop_loss':
                            self.refresh_notify_var.set(
                                f"❗ Stop-loss triggered: Sold {order['amount']} {order['from_token']} at ~{current_price:.6f}"
                            )
                        else:
                            self.refresh_notify_var.set(
                                f"✓ {order['order_type'].replace('_', ' ').title()} order filled at ~{current_price:.6f} USDC"
                            )
                        self.root.after(3000, lambda: self.refresh_notify_var.set(""))
                        
                except Exception as e:
                    print(f"Error checking order {order['id']}: {str(e)}")
                    continue
            
            # Remove executed orders from pending list
            for order_id in executed_orders:
                self.logger.remove_pending_order(order_id)
                
            # Update balances if any orders were executed
            if executed_orders:
                self._update_balance_display(initial_load=True)
                    
        except Exception as e:
            self.status_var.set(f"Order check error: {str(e)}")
            print(f"Error checking pending orders: {str(e)}")
                    
    def _get_price_info_for_tokens(self, force_query=False):
        from_token = self.from_token_var.get()
        to_token = self.to_token_var.get()
        
        # Use a short cache to avoid repeated calculations
        cache_key = f"{from_token}_{to_token}"
        current_time = time.time()
        
        # If not forcing a query and a cached entry exists within the last price update
        if not force_query and hasattr(self, '_price_info_cache') and cache_key in self._price_info_cache:
            cache_entry = self._price_info_cache[cache_key]
            if current_time - cache_entry['timestamp'] < 30:  # Use cache if <30s old
                return cache_entry['data'], cache_entry['is_reversed']
          
        # Determine the correct pair format to query
        if from_token in self.base_tokens and to_token == self.quote_token:
            # Selling base for quote (e.g., BTC/USDC)
            pair = f"{from_token}/{to_token}"
            is_reversed = False
        elif from_token == self.quote_token and to_token in self.base_tokens:
            # Selling quote for base (e.g., USDC/BTC)
            pair = f"{to_token}/{from_token}"
            is_reversed = True
        else:
            raise ValueError(f"Invalid token pair for limit order: {from_token}/{to_token}")
        
        # Get price info
        price_info = self.client.get_pool_price(pair)
        
        return price_info, is_reversed

    def _auto_update_expected_output(self):
        """Auto-update the expected output (called from the update thread)"""
        # Only update if there's an input amount and the form hasn't been manually edited
        if self.order_type_var.get() == "market":
            if not self.min_out_manually_set and self.amount_in_var.get().strip():
                # Temporarily set a flag to show we're doing an auto update
                self.refresh_notify_var.set("Auto-updating output values...")
                
                # Update the min out calculation
                self._update_min_out_hint()
                
                # Clear the notification after a short delay
                self.root.after(1500, lambda: self.refresh_notify_var.set(""))

    def _execute_order(self):
        """Execute order based on selected type"""
        order_type = self.order_type_var.get()
        
        if order_type == "market":
            self._execute_market_order()
        elif order_type == "limit":
            self._execute_limit_order()
        else:  # stop_loss
            self._execute_stop_loss_order()
    

    def _execute_market_order(self):
        """Execute a market order with enhanced transaction logging"""
        try:
            # Get form values
            from_token = self.from_token_var.get()
            to_token = self.to_token_var.get()
            
            # Validate amount
            try:
                amount = float(self.amount_in_var.get())
                if amount <= 0:
                    raise ValueError("Amount must be positive")
            except ValueError:
                self.status_var.set("Error: Invalid amount")
                return
            
            # Get minimum output amount if specified
            min_out = None
            if self.min_out_var.get().strip():
                try:
                    min_out = float(self.min_out_var.get())
                    if min_out <= 0:
                        raise ValueError("Minimum output must be positive")
                except ValueError:
                    self.status_var.set("Error: Invalid minimum output")
                    return
                    
            # Calculate slippage-based min_out if not manually specified
            if min_out is None and self.order_type_var.get() == "market":
                try:
                    slippage_pct = float(self.slippage_var.get())
                    
                    # Use the current market price to calculate expected output
                    price_info, is_reversed = self._get_price_info_for_tokens()
                    
                    if not is_reversed:
                        # Selling base for quote (e.g., BTC → USDC)
                        expected_out = amount * price_info['base_per_quote']
                    else:
                        # Selling quote for base (e.g., USDC → BTC)
                        expected_out = amount * price_info['quote_per_base']
                    
                    # Apply slippage tolerance
                    min_out = expected_out * (1 - slippage_pct/100)
                except Exception as e:
                    print(f"Error calculating min_out: {e}")
                    # Continue without min_out
            
            # Execute the swap
            result = self.client.execute_market_swap(from_token, to_token, amount, min_out)
            
            if result['success']:
                # Create an initial transaction record with expected values
                tx_data = {
                    'timestamp': datetime.now().isoformat(),
                    'tx_hash': result['tx_hash'],
                    'from_token': from_token,
                    'to_token': to_token,
                    'amount_in': amount,
                    'expected_amount_out': min_out if min_out is not None else None,
                    'order_type': 'market',
                    'status': 'executed',
                    'actual_amount_out': None,
                    'execution_price': None
                }
                
                # Log the transaction with expected values
                self.logger.log_transaction(tx_data)
                
                # Clear the form fields
                self.amount_in_var.set("")
                self.min_out_var.set("")
                self.min_out_manually_set = False
                
                # Start a background task to query actual transaction details
                self._query_actual_transaction(result['tx_hash'])
                
                # Update status
                self.status_var.set(f"Order executed - TX Hash: {result['tx_hash']}")
                
                # Force balance update
                self.root.after(2000, lambda: self._update_balance_display(initial_load=True))
            else:
                # Update status with error message
                self.status_var.set(f"Error: {result.get('error', 'Unknown error')}")
                
        except Exception as e:
            self.status_var.set(f"Error: {str(e)}")
            print(f"Error executing market order: {e}")

    def _query_actual_transaction(self, tx_hash):
        """Query actual transaction details and update the transaction log"""
        if tx_hash.startswith('order-'):
            # Skip synthetic transactions
            return
            
        def query_and_update():
            # Wait a few seconds for the transaction to be confirmed
            time.sleep(3)
            
            try:
                # Try up to 3 times with increasing delay to get tx details
                max_attempts = 3
                attempt = 0
                
                while attempt < max_attempts:
                    # Query the transaction details
                    tx_details = self.query_transaction_details(tx_hash)
                    
                    if tx_details:
                        # Update the transaction with actual values
                        updated_data = {
                            'actual_amount_out': tx_details['amount_out'],
                            'execution_price': tx_details['execution_price'],
                            'token_out_denom': tx_details['denom_out'],
                            'token_in_denom': tx_details['denom_in'],
                            'amount_in_raw': tx_details['amount_in_raw'],
                            'amount_out_raw': tx_details['amount_out_raw']
                        }
                        
                        success = self.logger.update_transaction(tx_hash, updated_data)
                        
                        if success:
                            # Update UI if transactions view is visible
                            if self.current_view == 'transactions' and hasattr(self, 'transactions_tree'):
                                self.root.after(0, self._update_transactions_list)
                                
                            # Show a notification if on main view
                            if self.current_view == 'main':
                                price_str = f"{tx_details['execution_price']:.6f}" if tx_details['execution_price'] else "unknown"
                                self.refresh_notify_var.set(f"✓ Transaction updated with actual values: {tx_details['amount_out']:.6f} {tx_details['token_out']} at {price_str}")
                                self.root.after(3000, lambda: self.refresh_notify_var.set(""))
                                
                            return
                    
                    # Increase delay with each attempt
                    attempt += 1
                    time.sleep(2 * attempt)  # 2s, 4s, 6s
                    
                # After all attempts, show a notification
                self.status_var.set("Unable to get actual transaction details after multiple attempts")
                
            except Exception as e:
                print(f"Error querying actual transaction details: {e}")
        
        # Run the query in a background thread
        threading.Thread(target=query_and_update, daemon=True).start()
    
    def _execute_stop_loss_order(self):
        """Create a stop-loss order"""
        try:
            from_token = self.from_token_var.get()
            to_token = self.to_token_var.get()
            
            # Validate that from_token is a base token (not USDC)
            # Stop-loss orders should only be for selling assets when price drops
            if from_token == self.quote_token:
                self.status_var.set("Error: Stop-loss orders can only be used to sell assets when price drops")
                return
                
            # Validate amount
            try:
                amount = float(self.amount_in_var.get())
                if amount <= 0:
                    raise ValueError("Amount must be positive")
            except ValueError:
                self.status_var.set("Error: Invalid amount")
                return
            
            # Validate stop price
            try:
                stop_price = float(self.stop_price_var.get())
                if stop_price <= 0:
                    raise ValueError("Stop price must be positive")
            except ValueError:
                self.status_var.set("Error: Invalid stop price")
                return
                
            # Validate that stop price is below current price
            pair = f"{from_token}/{to_token}"
            current_price_info = self.client.get_pool_price(pair)
            current_price = current_price_info['base_per_quote']
            
            if stop_price >= current_price:
                self.status_var.set(f"Error: Stop price ({stop_price}) must be below current price ({current_price:.6f})")
                return
                
            # Create order
            order_id = f"order-{self.order_id_counter}"
            self.order_id_counter += 1
            
            order_data = {
                'id': order_id,
                'timestamp': datetime.now().isoformat(),
                'from_token': from_token,
                'to_token': to_token,
                'amount': amount,
                'stop_price': stop_price,
                'order_type': 'stop_loss',
                'status': 'pending'
            }
            
            self.logger.add_pending_order(order_data)
            self.status_var.set(f"Stop-loss order {order_id} created at {stop_price} {to_token}")
            
            # Clear form
            self.amount_in_var.set("")
            self.stop_price_var.set("")
            
        except Exception as e:
            self.status_var.set(f"Error: {str(e)}")
            print(f"Error creating stop-loss order: {e}")
    
    def _execute_limit_order(self):
        """Create a limit order"""
        try:
            from_token = self.from_token_var.get()
            to_token = self.to_token_var.get()
            
            # Validate amount
            try:
                amount = float(self.amount_in_var.get())
                if amount <= 0:
                    raise ValueError("Amount must be positive")
            except ValueError:
                self.status_var.set("Error: Invalid amount")
                return
            
            # Validate limit price
            try:
                limit_price = float(self.limit_price_var.get())
                if limit_price <= 0:
                    raise ValueError("Price must be positive")
            except ValueError:
                self.status_var.set("Error: Invalid price")
                return
            
            # Get min output (auto-filled from estimate)
            try:
                min_out = float(self.min_out_var.get()) if self.min_out_var.get().strip() else None
                if min_out is not None and min_out <= 0:
                    raise ValueError("Minimum output must be positive")
            except ValueError:
                self.status_var.set("Error: Invalid minimum output")
                return
                
            # Determine order type
            if from_token == self.quote_token and to_token in self.base_tokens:
                order_type = "buy_limit"
            elif from_token in self.base_tokens and to_token == self.quote_token:
                order_type = "sell_limit"
            else:
                self.status_var.set("Error: Invalid pair for limit order")
                return
        
            # Create order
            order_id = f"order-{self.order_id_counter}"
            self.order_id_counter += 1
            
            order_data = {
                'id': order_id,
                'timestamp': datetime.now().isoformat(),
                'from_token': from_token,
                'to_token': to_token,
                'amount': amount,
                'limit_price': limit_price,
                'min_out': min_out,  # Store the min_out for execution
                'order_type': order_type,
                'status': 'pending'
            }
            
            self.logger.add_pending_order(order_data)
            self.status_var.set(f"Limit order {order_id} created")
            
            # Clear form
            self.amount_in_var.set("")
            self.limit_price_var.set("")
            self.min_out_var.set("")
            self.min_out_manually_set = False
            
        except Exception as e:
            self.status_var.set(f"Error: {str(e)}")

    def query_transaction_details(self, tx_hash):
        """Query the blockchain for exact transaction details using REST API"""
        try:
            # Skip querying for synthetic transactions (like pending orders)
            if tx_hash.startswith('order-'):
                return None
            
            # Use requests library to query the Osmosis REST API
            import requests
            
            # Base URL for Osmosis LCD API
            base_url = "https://lcd.osmosis.zone"
            
            # Endpoint for transaction details
            tx_url = f"{base_url}/cosmos/tx/v1beta1/txs/{tx_hash}"
            
            # Make the request
            response = requests.get(tx_url)
            
            # Check if request was successful
            if response.status_code != 200:
                print(f"Error querying transaction {tx_hash}: HTTP {response.status_code}")
                print(f"Response: {response.text}")
                return None
            
            # Parse the response
            tx_data = response.json()
            
            # Find token swap events
            token_swapped_events = [
                event for event in tx_data.get('tx_response', {}).get('events', [])
                if event.get('type') == 'token_swapped'
            ]
            
            # No swap events found
            if not token_swapped_events:
                print(f"No swap data found in transaction {tx_hash}")
                return None
            
            # Process the first swap event
            swap_result = token_swapped_events[0]
            
            # Extract attributes from the event
            event_attrs = {attr['key']: attr['value'] for attr in swap_result.get('attributes', [])}
            
            # Identify tokens in and out
            tokens_in = event_attrs.get('tokens_in', '')
            tokens_out = event_attrs.get('tokens_out', '')
            
            # Use the client's method to parse token amounts
            amount_in_parts = self.client._parse_token_amount(tokens_in)
            amount_out_parts = self.client._parse_token_amount(tokens_out)
            
            if not amount_in_parts or not amount_out_parts:
                print(f"Could not parse token amounts for {tx_hash}")
                return None
            
            # Convert to human-readable amounts
            amount_in = self.client._convert_to_human_readable(amount_in_parts['amount'], amount_in_parts['denom'])
            amount_out = self.client._convert_to_human_readable(amount_out_parts['amount'], amount_out_parts['denom'])
            
            # Calculate execution price
            execution_price = None
            from_token = self.client._get_token_symbol(amount_in_parts['denom'])
            to_token = self.client._get_token_symbol(amount_out_parts['denom'])
            
            # Check for base tokens 
            base_tokens = ["BTC", "ETH", "OSMO"]
            
            if amount_in > 0:
                if from_token in base_tokens and to_token == "USDC":
                    # Selling base token for USDC (e.g., BTC/USDC)
                    execution_price = amount_out / amount_in
                elif from_token == "USDC" and to_token in base_tokens:
                    # Buying base token with USDC (e.g., USDC/BTC)
                    execution_price = amount_in / amount_out
            
            # Try to get original transaction message for additional context
            original_msg = None
            for msg in tx_data.get('tx', {}).get('body', {}).get('messages', []):
                if msg.get('@type') == '/osmosis.poolmanager.v1beta1.MsgSwapExactAmountIn':
                    original_msg = msg
                    break
            
            return {
                'amount_in_raw': amount_in_parts['amount'],
                'denom_in': amount_in_parts['denom'],
                'amount_out_raw': amount_out_parts['amount'],
                'denom_out': amount_out_parts['denom'],
                'amount_in': amount_in,
                'amount_out': amount_out,
                'token_in': from_token,
                'token_out': to_token,
                'execution_price': execution_price,
                'pool_id': event_attrs.get('pool_id'),
                'min_out_amount': original_msg.get('token_out_min_amount') if original_msg else None
            }
            
        except Exception as e:
            print(f"Error processing transaction {tx_hash}: {str(e)}")
            return None
                

            
    def _show_transactions(self):
        """Show the transaction history view"""
        if self.current_view == 'transactions':
            return
            
        # Hide all frames
        self.main_frame.pack_forget()
        if hasattr(self, 'pending_orders_frame'):
            self.pending_orders_frame.pack_forget()
        
        # Show transactions frame (create only if needed)
        if not hasattr(self, 'transactions_frame'):
            self._create_transactions_view()
        else:
            # Update transaction list AFTER showing the frame
            self.root.after(10, self._update_transactions_list)
        
        self.transactions_frame.pack(fill=tk.BOTH, expand=True)
        self.current_view = 'transactions'

    def _copy_selected_tx_hash(self):
        """Copy selected transaction hash to clipboard"""
        selected = self.transactions_tree.selection()
        if selected:
            tx_hash = self.transactions_tree.item(selected[0], 'values')[8]
            self.root.clipboard_clear()
            self.root.clipboard_append(tx_hash)
            
            # Visual feedback
            self.refresh_notify_var.set(f"✓ Copied TX hash: {tx_hash[:10]}...")
            self.root.after(3000, lambda: self.refresh_notify_var.set(""))
    
    def _create_transactions_view(self):
        """Create the transactions history view with enhanced display"""
        self.transactions_frame = ttk.Frame(self.root, padding="20")
        
        # Title and back button
        title_frame = ttk.Frame(self.transactions_frame)
        title_frame.pack(fill=tk.X, pady=(0, 20))
        
        back_button = ttk.Button(title_frame, text="← Back", command=self._show_main_view)
        back_button.pack(side=tk.LEFT)
        
        title_label = ttk.Label(title_frame, text="Transaction History", style='Title.TLabel')
        title_label.pack(side=tk.LEFT, padx=10)
        
        # Transactions list
        list_frame = ttk.Frame(self.transactions_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create a Treeview widget with scrollbars
        tree_scroll = ttk.Scrollbar(list_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.transactions_tree = ttk.Treeview(
            list_frame,
            yscrollcommand=tree_scroll.set,
            selectmode="extended",
            columns=("timestamp", "type", "from", "amount_in", "to", "amount_out", "price", "status", "tx_hash"),
            show="headings"
        )
        self.transactions_tree.pack(fill=tk.BOTH, expand=True)
        
        tree_scroll.config(command=self.transactions_tree.yview)
        
        # Define columns
        self.transactions_tree.heading("timestamp", text="Time", anchor=tk.W)
        self.transactions_tree.heading("type", text="Type", anchor=tk.W)
        self.transactions_tree.heading("from", text="From", anchor=tk.W)
        self.transactions_tree.heading("amount_in", text="Amount In", anchor=tk.W)
        self.transactions_tree.heading("to", text="To", anchor=tk.W)
        self.transactions_tree.heading("amount_out", text="Amount Out", anchor=tk.W)
        self.transactions_tree.heading("price", text="Price", anchor=tk.W)
        self.transactions_tree.heading("status", text="Status", anchor=tk.W)
        self.transactions_tree.heading("tx_hash", text="TX Hash", anchor=tk.W)
        
        # Configure column widths
        self.transactions_tree.column("timestamp", width=100, stretch=tk.NO)
        self.transactions_tree.column("type", width=70, stretch=tk.NO)
        self.transactions_tree.column("from", width=50, stretch=tk.NO)
        self.transactions_tree.column("amount_in", width=90, stretch=tk.NO)
        self.transactions_tree.column("to", width=50, stretch=tk.NO)
        self.transactions_tree.column("amount_out", width=90, stretch=tk.NO)
        self.transactions_tree.column("price", width=80, stretch=tk.NO)
        self.transactions_tree.column("status", width=70, stretch=tk.NO)
        self.transactions_tree.column("tx_hash", width=100, stretch=tk.YES)
        
        # Add right-click menu for copying TX hash and viewing details
        self.transactions_tree.bind("<Button-3>", self._on_transaction_right_click)
        self.transactions_tree.bind("<Double-1>", self._on_transaction_double_click)
    
        # Create context menu
        self.tx_menu = tk.Menu(self.transactions_tree, tearoff=0)
        self.tx_menu.add_command(label="Copy TX Hash", command=self._copy_selected_tx_hash)
        self.tx_menu.add_command(label="View Details", command=self._show_transaction_details)
        self.tx_menu.add_command(label="Refresh Actual Values", command=self._refresh_transaction_actual_values)
        
        # Add a refresh button
        button_frame = ttk.Frame(self.transactions_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        refresh_button = ttk.Button(
            button_frame,
            text="Refresh List",
            command=self._update_transactions_list
        )
        refresh_button.pack(side=tk.LEFT)
        
        export_button = ttk.Button(
            button_frame,
            text="Export CSV",
            command=self._export_transactions_csv
        )
        export_button.pack(side=tk.RIGHT)
    
    def _update_transactions_list(self):
        """Update the transactions list with current data"""
        # Clear existing items (use detach for better performance)
        children = self.transactions_tree.get_children()
        if children:
            self.transactions_tree.delete(*children)
        
        # Get only the MOST RECENT transactions
        transactions = self.logger.get_transactions()[-50:]  # Limited to 50 most recent
        
        # Sort newest first
        transactions.sort(key=lambda tx: tx['timestamp'], reverse=True)
        
        # Add transactions to the treeview
        for tx in transactions:
            # Format timestamp
            timestamp = datetime.fromisoformat(tx['timestamp']).strftime("%Y-%m-%d %H:%M")
            
            # Determine type
            order_type = tx.get('order_type', 'market').capitalize()
            
            # Format the amount_out - show actual if available, otherwise expected
            actual_amount = tx.get('actual_amount_out')
            expected_amount = tx.get('expected_amount_out')
            amount_out_value = tx.get('amount_out', expected_amount) # For compatibility with older logs
            
            if actual_amount is not None:
                # Format with token-specific precision
                if tx['to_token'] == "BTC":
                    amount_out_display = f"{actual_amount:.8f}"
                else:
                    amount_out_display = f"{actual_amount:.6f}"
            elif amount_out_value is not None:
                # Use expected with indication
                if tx['to_token'] == "BTC":
                    amount_out_display = f"{amount_out_value:.8f} (est)"
                else:
                    amount_out_display = f"{amount_out_value:.6f} (est)"
            else:
                amount_out_display = "N/A"
                
            # Format the price - show actual if available
            execution_price = tx.get('execution_price')
            if execution_price is not None:
                price_display = f"{execution_price:.6f}"
            else:
                # Try to calculate from expected values
                if order_type.lower() == 'limit':
                    price_display = f"{tx.get('limit_price', 'N/A')}"
                elif amount_out_value is not None and tx.get('amount_in', 0) > 0:
                    # For market orders, calculate from expected values
                    # This is different from execution price due to slippage
                    if tx['from_token'] in self.base_tokens and tx['to_token'] == self.quote_token:
                        # Selling base for quote
                        calc_price = amount_out_value / tx.get('amount_in', 1)
                        price_display = f"{calc_price:.6f} (est)"
                    elif tx['from_token'] == self.quote_token and tx['to_token'] in self.base_tokens:
                        # Buying base with quote
                        calc_price = tx.get('amount_in', 0) / amount_out_value
                        price_display = f"{calc_price:.6f} (est)"
                    else:
                        price_display = "N/A"
                else:
                    price_display = "N/A"
            
            # Add to treeview
            self.transactions_tree.insert("", tk.END, values=(
                timestamp,
                order_type,
                tx['from_token'],
                f"{tx['amount_in']:.6f}",
                tx['to_token'],
                amount_out_display,
                price_display,
                tx.get('status', 'completed').capitalize(),
                tx['tx_hash']
            ))
    

    def _on_transaction_right_click(self, event):
        """Handle right-click on transaction row"""
        item = self.transactions_tree.identify_row(event.y)
        if item:
            self.transactions_tree.selection_set(item)
            try:
                self.tx_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.tx_menu.grab_release()
    
    def _on_transaction_double_click(self, event):
        """Handle double-click on transaction row"""
        item = self.transactions_tree.identify_row(event.y)
        if item:
            self.transactions_tree.selection_set(item)
            self._show_transaction_details()
    
    def _show_transaction_details(self):
        """Show detailed information for the selected transaction"""
        selected = self.transactions_tree.selection()
        if not selected:
            return
            
        # Get the transaction hash from the selected row
        tx_hash = self.transactions_tree.item(selected[0], 'values')[8]
        
        # Find the transaction in the log
        transactions = self.logger.get_transactions()
        tx_data = None
        
        for tx in transactions:
            if tx.get('tx_hash') == tx_hash:
                tx_data = tx
                break
                
        if not tx_data:
            messagebox.showinfo("Transaction Details", "Transaction not found in logs")
            return
            
        # Create a formatted details string
        details = [
            f"Transaction: {tx_hash}",
            f"Time: {datetime.fromisoformat(tx_data['timestamp']).strftime('%Y-%m-%d %H:%M:%S')}",
            f"Type: {tx_data.get('order_type', 'Market').capitalize()}",
            f"Status: {tx_data.get('status', 'Completed').capitalize()}",
            "",
            f"From: {tx_data['amount_in']} {tx_data['from_token']}",
        ]
        
        # Add expected vs actual output if available
        if tx_data.get('actual_amount_out') is not None:
            details.append(f"To (Actual): {tx_data['actual_amount_out']} {tx_data['to_token']}")
            if tx_data.get('expected_amount_out') is not None:
                details.append(f"To (Expected): {tx_data['expected_amount_out']} {tx_data['to_token']}")
        else:
            amount_out = tx_data.get('amount_out', tx_data.get('expected_amount_out'))
            if amount_out is not None:
                details.append(f"To (Expected): {amount_out} {tx_data['to_token']}")
            else:
                details.append(f"To: Unknown amount of {tx_data['to_token']}")
        
        # Add price information
        if tx_data.get('execution_price') is not None:
            details.append(f"Execution Price: {tx_data['execution_price']:.6f} {tx_data['to_token']}/{tx_data['from_token']}")
            
            # Add slippage information if we have both expected and actual
            if tx_data.get('expected_amount_out') is not None and tx_data.get('actual_amount_out') is not None:
                expected = tx_data['expected_amount_out']
                actual = tx_data['actual_amount_out']
                slippage_pct = ((expected - actual) / expected) * 100 if expected > 0 else 0
                details.append(f"Slippage: {slippage_pct:.2f}%")
        elif tx_data.get('order_type') == 'limit' and tx_data.get('limit_price') is not None:
            details.append(f"Limit Price: {tx_data['limit_price']:.6f}")
        
        # Add raw blockchain data if available
        if tx_data.get('amount_in_raw') is not None:
            details.append("")
            details.append("Raw Blockchain Data:")
            details.append(f"Amount In: {tx_data['amount_in_raw']} {tx_data.get('token_in_denom', 'unknown')}")
            details.append(f"Amount Out: {tx_data['amount_out_raw']} {tx_data.get('token_out_denom', 'unknown')}")
        
        # Show details in a dialog
        details_text = "\n".join(details)
        
        # Create a custom dialog
        details_dialog = tk.Toplevel(self.root)
        details_dialog.title("Transaction Details")
        details_dialog.geometry("500x400")
        details_dialog.configure(background="#151733")  # Dark blue background
        details_dialog.grab_set()  # Make dialog modal
        
        # Add padding
        frame = ttk.Frame(details_dialog, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Add scrollable text area
        text_scroll = ttk.Scrollbar(frame)
        text_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        text_area = tk.Text(
            frame, 
            wrap=tk.WORD, 
            width=60, 
            height=20, 
            yscrollcommand=text_scroll.set,
            background="#202442",  # Dark blue-grey
            foreground="white",
            relief=tk.FLAT,
            font=("Consolas", 10)
        )
        text_area.pack(fill=tk.BOTH, expand=True)
        text_scroll.config(command=text_area.yview)
        
        # Insert details text
        text_area.insert("1.0", details_text)
        text_area.config(state=tk.DISABLED)  # Make read-only
        
        # Add buttons at the bottom
        button_frame = ttk.Frame(details_dialog, padding="10")
        button_frame.pack(fill=tk.X)
        
        # Refresh button only for non-synthetic transactions
        if not tx_hash.startswith('order-'):
            refresh_button = ttk.Button(
                button_frame,
                text="Refresh Values",
                command=lambda: self._refresh_tx_values_from_dialog(details_dialog, tx_hash)
            )
            refresh_button.pack(side=tk.LEFT, padx=5)
        
        copy_button = ttk.Button(
            button_frame,
            text="Copy TX Hash",
            command=lambda: self._copy_tx_hash_from_dialog(details_dialog, tx_hash)
        )
        copy_button.pack(side=tk.LEFT, padx=5)
        
        close_button = ttk.Button(
            button_frame,
            text="Close",
            command=details_dialog.destroy
        )
        close_button.pack(side=tk.RIGHT, padx=5)

    
    def _copy_tx_hash_from_dialog(self, dialog, tx_hash):
        """Copy transaction hash from the dialog"""
        self.root.clipboard_clear()
        self.root.clipboard_append(tx_hash)
        
        # Show confirmation message
        label = ttk.Label(
            dialog, 
            text="✓ Hash copied to clipboard!", 
            background="#151733", 
            foreground="#4ade80"
        )
        label.pack(pady=5)
        dialog.after(2000, label.destroy)
    
    def _refresh_tx_values_from_dialog(self, dialog, tx_hash):
        """Refresh transaction values from the details dialog"""
        # Create a progress message
        progress_label = ttk.Label(
            dialog, 
            text="Refreshing transaction details...", 
            background="#151733", 
            foreground="#a78bfa"
        )
        progress_label.pack(pady=5)
        
        def refresh_task():
            # Query the transaction
            tx_details = self.client.query_transaction_details(tx_hash)
            
            if tx_details:
                # Update the transaction with actual values
                updated_data = {
                    'actual_amount_out': tx_details['amount_out'],
                    'execution_price': tx_details['execution_price'],
                    'token_out_denom': tx_details['denom_out'],
                    'token_in_denom': tx_details['denom_in'],
                    'amount_in_raw': tx_details['amount_in_raw'],
                    'amount_out_raw': tx_details['amount_out_raw']
                }
                
                success = self.logger.update_transaction(tx_hash, updated_data)
                
                if success:
                    # Update UI
                    self._update_transactions_list()
                    
                    # Close the old dialog and show a new one with updated data
                    dialog.destroy()
                    self.root.after(100, lambda: self._show_transaction_details())
                    
                    return
            
            # If we get here, there was an error
            progress_label.config(text="Error refreshing transaction details", foreground="#f87171")
            dialog.after(2000, progress_label.destroy)
        
        # Run the refresh task in a background thread
        threading.Thread(target=refresh_task, daemon=True).start()
    
    def _refresh_transaction_actual_values(self):
        """Refresh actual values for the selected transaction"""
        selected = self.transactions_tree.selection()
        if not selected:
            return
            
        # Get the transaction hash
        tx_hash = self.transactions_tree.item(selected[0], 'values')[8]
        
        # Don't try to refresh synthetic transactions
        if tx_hash.startswith('order-'):
            messagebox.showinfo("Refresh Transaction", "Cannot refresh synthetic transactions")
            return
        
        # Update status
        self.status_var.set(f"Refreshing transaction {tx_hash}...")
        
        # Query in background
        self._query_actual_transaction(tx_hash)
    
    def _export_transactions_csv(self):
        """Export transactions to CSV file"""
        try:
            # Ask for file location
            filename = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                title="Export Transactions"
            )
            
            if not filename:
                return  # User canceled
                
            # Get transactions
            transactions = self.logger.get_transactions()
            
            # Sort by timestamp (newest first)
            transactions.sort(key=lambda tx: tx['timestamp'], reverse=True)
            
            # Define CSV headers
            headers = [
                "Date",
                "Type",
                "From Token",
                "Amount In",
                "To Token",
                "Amount Out (Expected)",
                "Amount Out (Actual)",
                "Price (Expected)",
                "Price (Actual)",
                "Status",
                "Transaction Hash"
            ]
            
            # Write CSV file
            with open(filename, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(headers)
                
                for tx in transactions:
                    # Calculate expected price if not explicitly stored
                    expected_price = None
                    if tx.get('expected_amount_out') and tx.get('amount_in'):
                        if tx['from_token'] in self.base_tokens and tx['to_token'] == self.quote_token:
                            # Selling base for quote
                            expected_price = tx['expected_amount_out'] / tx['amount_in']
                        elif tx['from_token'] == self.quote_token and tx['to_token'] in self.base_tokens:
                            # Buying base with quote
                            expected_price = tx['amount_in'] / tx['expected_amount_out']
                    
                    # Format timestamp
                    date = datetime.fromisoformat(tx['timestamp']).strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Write row
                    writer.writerow([
                        date,
                        tx.get('order_type', 'market').capitalize(),
                        tx['from_token'],
                        tx['amount_in'],
                        tx['to_token'],
                        tx.get('expected_amount_out', tx.get('amount_out')),  # Fallback for compatibility
                        tx.get('actual_amount_out'),
                        expected_price,
                        tx.get('execution_price'),
                        tx.get('status', 'completed').capitalize(),
                        tx['tx_hash']
                    ])
                    
            self.status_var.set(f"Exported {len(transactions)} transactions to {filename}")
            
        except Exception as e:
            self.status_var.set(f"Error exporting transactions: {str(e)}")
            print(f"Error exporting transactions: {e}")
            

    def _show_main_view(self):
        """Return to the main trading view"""
        if self.current_view == 'main':
            return
            
        # Hide current frame based on what's visible
        if hasattr(self, 'transactions_frame') and self.transactions_frame.winfo_ismapped():
            self.transactions_frame.pack_forget()
        if hasattr(self, 'pending_orders_frame') and self.pending_orders_frame.winfo_ismapped():
            self.pending_orders_frame.pack_forget()
    
        # Show main frame
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.current_view = 'main'
        
        # Run cleanup when switching views
        self._cleanup_caches()

def main():
    root = tk.Tk()
    root.update_idletasks()
    
    # Performance optimizations
    root.option_add('*tearOff', False)
    
    try:
        root.tk.call('tk', 'useinputmethods', '0')
    except:
        pass
    
    app = OsmosisTraderUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
