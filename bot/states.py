from aiogram.fsm.state import State, StatesGroup

class DocumentStates(StatesGroup):
    waiting_for_doc_language = State()  # Hujjat tili tanlash
    waiting_for_topic = State()
    waiting_for_author_name = State()  # Ism Familiya kiritish
    waiting_for_slide_count = State()
    waiting_for_page_count = State()
    waiting_for_course_work_pages = State()  # Kurs ishi sahifa/bo'lim tanlash
    waiting_for_outline_choice = State()
    waiting_for_manual_outline = State()
    waiting_for_outline_confirmation = State()
    waiting_for_template = State()
    waiting_for_plan_slide_choice = State()  # Reja varaq so'rovi (taqdimot uchun)
    waiting_for_references_choice = State()

class PaymentStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_screenshot = State()

class SettingsStates(StatesGroup):
    waiting_for_promocode = State()

class AdminStates(StatesGroup):
    # Payment management
    reviewing_payment = State()

    # Channel management
    waiting_for_channel_id = State()
    waiting_for_channel_username = State()
    waiting_for_channel_title = State()

    # Promocode management
    waiting_for_promocode = State()
    waiting_for_deactivate_promocode = State()

    # Broadcast
    waiting_for_broadcast_message = State()
    waiting_for_broadcast_target = State()

    # Settings
    waiting_for_new_price = State()

    # Sample management
    waiting_for_sample_file = State()
    waiting_for_sample_title = State()
    waiting_for_sample_description = State()

    # Block user states
    waiting_for_block_user = State()
    waiting_for_block_reason = State()

    # Mass gift
    waiting_for_gift_amount = State()

class PaymentResubmitStates(StatesGroup):
    waiting_for_receipt = State()
    waiting_for_amount = State()