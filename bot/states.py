from aiogram.fsm.state import State, StatesGroup

class DocumentStates(StatesGroup):
    waiting_for_topic = State()
    waiting_for_slide_count = State()
    waiting_for_page_count = State()
    waiting_for_promocode_choice = State()
    waiting_for_promocode = State()

class PaymentStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_screenshot = State()

class AdminStates(StatesGroup):
    # Payment management
    reviewing_payment = State()
    
    # Channel management
    waiting_for_channel_id = State()
    waiting_for_channel_username = State()
    waiting_for_channel_title = State()
    
    # Promocode management
    waiting_for_promocode = State()
    
    # Broadcast
    waiting_for_broadcast_message = State()
    waiting_for_broadcast_target = State()
    
    # Settings
    waiting_for_new_price = State()
