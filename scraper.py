import base64
import json
import os
import time
import requests
from bs4 import BeautifulSoup

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("GITHUB_REPOSITORY")
BRANCH = "Control"

TARGET_RECIPES = 20000
CHUNK_SIZE = 100

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def log(message):
  """دالة مخصصة للطباعة الفورية مع فرض إظهار السجلات على سيرفر جيت هاب"""
  print(message, flush=True)


def get_recipe_urls():
  log("[*] جاري توليد وتجهيز قائمة روابط الوصفات المستهدفة...")
  urls = []
  # يمكنك تعديل نمط الروابط هنا ليطابق هيكل الموقع المستهدف بدقة
  for i in range(1, TARGET_RECIPES + 1):
    urls.append(f"https://www.allrecipes.com/recipe/{i}/example/")
  log(
      f"[+] تم تجهيز قائمة إجمالية تضم {len(urls)} رابطاً للبدء في الفحص"
      " والسحب."
  )
  return urls


def extract_recipe_data(url, index):
  """استخراج بيانات الوصفة بدقة من وسوم JSON-LD مع تسجيل تفصيلي"""
  log(
      f"--- [فحص الوصفة رقم {index}] جاري الاتصال بالرابط:"
      f" {url.split('//')[-1]}"
  )
  try:
    response = requests.get(url, headers=HEADERS, timeout=15)
    log(f"    [إستجابة] كود الحالة (Status Code): {response.status_code}")

    if response.status_code != 200:
      log(
          "    [-] تحذير: الرابط لا يعود ببيانات سليمة (خطأ أو غير موجود)، جاري"
          " التخطي."
      )
      return None

    soup = BeautifulSoup(response.text, "html.parser")
    json_ld_scripts = soup.find_all("script", type="application/ld+json")
    log(
        f"    [تحليل] تم العثور على {len(json_ld_scripts)} عنصر JSON-LD في"
        " الصفحة."
    )

    recipe_data = None
    for idx, script in enumerate(json_ld_scripts):
      try:
        data = json.loads(script.string)
        if isinstance(data, list):
          for item in data:
            if item.get("@type") == "Recipe":
              recipe_data = item
              break
        elif isinstance(data, dict):
          if data.get("@type") == "Recipe":
            recipe_data = data
          elif "@graph" in data:
            for item in data["@graph"]:
              if item.get("@type") == "Recipe":
                recipe_data = item
                break
        if recipe_data:
          break
      except Exception:
        continue

    if not recipe_data:
      log(
          "    [-] تنبيه: الصفحة لا تحتوي على هيكل وصفة (Recipe Schema)"
          " مطابق."
      )
      return None

    structured_recipe = {
        "name": recipe_data.get("name"),
        "description": recipe_data.get("description"),
        "image": recipe_data.get("image"),
        "prepTime": recipe_data.get("prepTime"),
        "cookTime": recipe_data.get("cookTime"),
        "totalTime": recipe_data.get("totalTime"),
        "category": recipe_data.get("recipeCategory"),
        "cuisine": recipe_data.get("recipeCuisine"),
        "ingredients": recipe_data.get("recipeIngredient", []),
        "instructions": [
            step.get("text")
            for step in recipe_data.get("recipeInstructions", [])
            if isinstance(step, dict) and "text" in step
        ],
        "nutrition": recipe_data.get("nutrition", {}),
        "source_url": url,
    }
    log(
        f"    [نجاح] تمت استخراج الوصفة بنجاح: '{structured_recipe['name']}'"
        " بكامل بياناتها."
    )
    return structured_recipe

  except Exception as e:
    log(f"    [خطأ استثنائي] حدث خطأ أثناء سحب الرابط: {e}")
    return None


def push_chunk_to_github(chunk_data, chunk_index):
  """رفع الملف المجمع مباشرة عبر GitHub API مع طباعة حالة الرفع"""
  file_path = f"recipe_chunks/chunk_{chunk_index}.json"
  log(
      f"\n>>> [رفع السيرفر] جاري تجهيز الـ Chunk رقم {chunk_index}"
      f" ({len(chunk_data)} وصفة) لرفعها مباشرة..."
  )

  if not GITHUB_TOKEN or not REPO_NAME:
    log(
        "    [خطأ فادح] مفتاح GITHUB_TOKEN أو اسم المستودع مفقود من بيئة"
        " التشغيل!"
    )
    return

  url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
  json_content = json.dumps(chunk_data, ensure_ascii=False, indent=4)
  encoded_content = base64.b64encode(json_content.encode("utf-8")).decode(
      "utf-8"
  )

  headers = {
      "Authorization": f"Bearer {GITHUB_TOKEN}",
      "Accept": "application/vnd.github+json",
  }

  log("    [GitHub API] التحقق مما إذا كان الملف موجوداً مسبقاً للتحديث...")
  get_resp = requests.get(url, headers=headers, params={"ref": BRANCH})
  sha = None
  if get_resp.status_code == 200:
    sha = get_resp.json().get("sha")
    log("    [GitHub API] الملف موجود مسبقاً، سيتم تحديثه (SHA متاح).")
  else:
    log("    [GitHub API] الملف جديد كلياً، سيتم إنشاؤه لأول مرة.")

  payload = {
      "message": (
          f"Add/Update recipe chunk {chunk_index} [Direct API Real-time]"
      ),
      "content": encoded_content,
      "branch": BRANCH,
  }
  if sha:
    payload["sha"] = sha

  log("    [GitHub API] إرسال طلب الرفع إلى خوادم جيت هاب...")
  put_resp = requests.put(url, headers=headers, json=payload)

  if put_resp.status_code in [200, 201]:
    log(
        f"[تم بنجاح] تم رفع ملف الـ Chunk بنجاح تام إلى المسار: {file_path} 🎉\n"
    )
  else:
    log(f"[فشل الرفع] خطأ من خوادم جيت هاب: {put_resp.text}\n")


def main():
  log("==================================================")
  log(" بدء تشغيل نظام سحب الوصفات الذكي (Real-time Logger Active)")
  log("==================================================")

  urls = get_recipe_urls()
  current_chunk = []
  chunk_index = 1
  processed_count = 0

  for idx, url in enumerate(urls, start=1):
    recipe = extract_recipe_data(url, idx)

    if recipe:
      current_chunk.append(recipe)
      processed_count += 1
      log(
          f"    [إحصائية] إجمالي الوصفات الناجحة الحالية:"
          f" {processed_count}/{TARGET_RECIPES}"
      )

    # عند اكتمال 100 وصفة، يتم إرسالها فوراً
    if len(current_chunk) == CHUNK_SIZE or (
        idx == len(urls) and current_chunk
    ):
      push_chunk_to_github(current_chunk, chunk_index)
      chunk_index += 1
      current_chunk = []

    # فاصل زمني منتظم لحماية السكربت من الحظر
    time.sleep(1.2)

  log("==================================================")
  log(
      f" انتهت عملية السحب بنجاح كامل! إجمالي الوصفات المعالجة:"
      f" {processed_count}"
  )
  log("==================================================")


if __name__ == "__main__":
  main()
