"""企業スポンサーへ手で送るメールの下書きを組み立てる

申し込みの内容で必要な節が変わるので、毎回人が選ぶと抜けが出る
組み立てた下書きをログ用チャンネルに出し、スタッフがコピーしてメールで送る
"""

from __future__ import annotations

from . import config
from .sheets import value_of

# 希望する特典の選択肢を見分ける文字列
BENEFIT_SLIDE = "スライドの配信"
BENEFIT_NOVELTY = "チラシ・ノベルティ"
BENEFIT_PITCH = "スポンサーピッチ"
BENEFIT_LT = "スポンサー枠LT発表"

# 「以前と同じでOK」と「Discordにてやりとり」を見分ける文字列
CONTACT_SAME = "以前と同じ"
CONTACT_DISCORD = "Discord"

# チラシ・ノベルティの受け渡し方法を見分ける文字列
DELIVERY_ADVANCE = "事前発送"
DELIVERY_ONSITE = "当日搬入"

# 前回の画像が見つからないときに、URLの代わりに出す文
NOT_FOUND = "（前回のロゴが見つかりません。スタッフが確認します）"

HEAD = """{{会社名}}
{{ご担当者氏名}} さま

お世話になっております。

この度はスポンサーへお申し込みいただき、誠にありがとうございます。
NGKにお力添えいただけること、大変うれしく思っております。

早速ですが、いくつかご確認とお願いがございます。"""

LOGO_SAME = """■ イベント告知ページへ掲載するロゴについて

前回ご提供いただいた以下のロゴをそのまま使用いたします。
{{ロゴURL}}

変更をご希望の場合は、お知らせください。"""

LOGO_NEW = """■ イベント告知ページへ掲載するロゴについて

イベント告知ページへ掲載するロゴをご提供ください。

ファイル形式：png, jpg, pdf, ai ※他の形式をご希望の場合はご相談ください
推奨解像度：768px × 768px

正方形でない画像をいただいた場合は、白色の余白を追加して正方形に整えて使用いたします。
また、掲載先に合わせて解像度を調整して使用いたします。"""

LT = """■ スポンサーLTのご発表について

ご発表者名およびLTタイトルが決まりましたら、以下のフォームよりご入力をお願いいたします。

https://docs.google.com/forms/d/e/1FAIpQLSc26h0vimSSZ03bjhZ6qKZIs9mCPxPgPXDAibM5pM83Rh2Sbw/viewform?usp=pp_url&entry.871443715=%E3%82%B9%E3%83%9D%E3%83%B3%E3%82%B5%E3%83%BCLT"""

PITCH = """■ スポンサーピッチについて

1枠15秒の口頭のみのご発表です。スライドはご利用いただけません。
告知や宣伝にご活用いただけます。営利目的、求人目的の内容も可能です。
お時間は15秒厳守でお願いいたします。15秒を経過しますと、そこで終了とさせていただきます。
ご発表者の皆様に壇上へお並びいただき、お一人ずつ順にご発表いただきます。
登壇のタイミングにつきましては、時期が近づきましたら改めてご連絡いたします。"""

SLIDE_SAME = """■ イベント休憩時間におけるスライド配信について

前回ご提供いただいたスライドをそのまま使用いたします。
変更をご希望の場合は、2026年12月31日までにお知らせください。"""

SLIDE_NEW = """■ イベント休憩時間におけるスライド配信について

イベント中に上映するスライドをご提出ください。

提出期限：2026年12月31日
ファイル形式：png, jpg, pdf, ai ※他の形式をご希望の場合はご相談ください
推奨解像度：1920px × 1080px
スライド数：1〜2枚

スライドの外周にロゴやテロップを重ねる場合がございます。
上下左右10%を除いた中央90%をセーフエリアとしてレイアウトしてください。"""

# 配布に必要な部数の目安。1社で全員配布と任意配布の両方を出す場合があるので、品物ごとに書く
NOVELTY_COUNT = """全員配布をご希望の品物は120部程度をご用意ください。
任意配布の品物はそれ以下でも構いません（先着順での配布となります）。
配布しきれなかった分は、返却できない場合がございますのでご了承ください。"""

NOVELTY_ADVANCE = f"""■ 当日配布のチラシ・ノベルティについて

事前発送をご希望いただいておりますので、2027年1月8日までに
下記の宛先までお送りください。

〒460-0007
愛知県名古屋市中区新栄一丁目29-23
アーバンドエル新栄 2階
有限会社来栖川電算 内
名古屋合同懇親会 実行委員会 宛

{NOVELTY_COUNT}"""

NOVELTY_ONSITE = """■ 当日配布のチラシ・ノベルティについて

当日搬入をご希望いただいております。
受付開始の15分ほど前までに会場へお持ちください。
当日搬入では、任意配布のチラシ・ノベルティのみ承っております。
部数は先着順での配布となりますので、お手持ちの数で構いません。
配布しきれなかった分は、返却できない場合がございますのでご了承ください。"""

CONNPASS = """■ connpassのお申し込みについて

スポンサーLTのご発表者を含め、当日ご参加いただく皆様につきましては、
お手数ですが下記ページよりお申し込みをお願いいたします。

昼の部：https://ngk.connpass.com/event/408358/
夜の部：https://ngk.connpass.com/event/408359/"""

INVOICE = """■ スポンサー費用について

イベント終了後にご請求いたします。
費用授受の代行を行う有限会社来栖川電算からのご請求となります。"""

TAIL = """ご不明点などございましたら、お気軽にお知らせください。
引き続きどうぞよろしくお願いいたします。"""


def build(record: dict[str, str]) -> str:
    """申し込みの内容に合う節だけを並べて、メールの下書きを組み立てる

    Args:
        record: 企業スポンサー申込の行の値

    Returns:
        そのままメールに貼れる本文
    """
    columns = config.COL_SPONSOR
    company = value_of(record, columns, "company")
    benefit = value_of(record, columns, "benefit")
    logo_contact = value_of(record, columns, "logo")
    slide_contact = value_of(record, columns, "slide")
    delivery = value_of(record, columns, "novelty_delivery")

    parts = [
        HEAD.replace("{{会社名}}", company).replace(
            "{{ご担当者氏名}}", value_of(record, columns, "owner")
        )
    ]

    if CONTACT_SAME in logo_contact:
        logo_url = config.SPONSOR_LOGO_URLS.get(company, NOT_FOUND)
        parts.append(LOGO_SAME.replace("{{ロゴURL}}", logo_url))
    else:
        parts.append(LOGO_NEW)
    if BENEFIT_LT in benefit:
        parts.append(LT)
    if BENEFIT_PITCH in benefit:
        parts.append(PITCH)
    if BENEFIT_SLIDE in benefit:
        parts.append(SLIDE_SAME if CONTACT_SAME in slide_contact else SLIDE_NEW)
    if BENEFIT_NOVELTY in benefit:
        if DELIVERY_ADVANCE in delivery:
            parts.append(NOVELTY_ADVANCE)
        elif DELIVERY_ONSITE in delivery:
            parts.append(NOVELTY_ONSITE)
    parts.append(CONNPASS)
    parts.append(INVOICE)
    parts.append(TAIL)
    return "\n\n".join(parts)
