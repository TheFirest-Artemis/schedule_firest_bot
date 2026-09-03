from aiogram import Router

from . import schedule, settings, start

router = Router()
router.include_router(start.router)
router.include_router(settings.router)
router.include_router(schedule.router)
