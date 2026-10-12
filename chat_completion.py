"""Reject present-turn rewrite announcements without content before any send binding."""
import re

_ANNOUNCEMENT = re.compile(
    r'^(?:(?:博士|抱歉|对不起|好|好的|嗯|行|那|那好|等一下|稍等|刚才那句不算|刚才说错了|刚才没说清楚)[，,。.!！：:\s]*)*'
    r'(?:我)?(?:现在|这就|马上|再|来)?(?:重新发|重发|重新说|重说|换个说法|换一句|再发|再说)'
    r'(?:一遍|一次|一句|一下|一条|个|给你|给你看|好了|吧|了|这句|这条|一条消息)*[，,。.!！：:\s]*$'
)


def require_complete_text(text):
    if _ANNOUNCEMENT.fullmatch(text.strip()):
        raise ValueError('unfinished_reply')


UNFINISHED_REPLY = {
    'error': 'unfinished_reply', 'sent': False,
    'instruction': '尚未发送，也未占用幂等编号。请在本轮直接给出完整修正内容，不先发“我重新发一句”，不等待群友再次催促；按原触发事件和原发送编号提交完整正文。UNKNOWN或已成功的真实发送仍须核对回执，不以改写为由盲目重发。'
}
