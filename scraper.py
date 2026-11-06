import base64
import json
import os
import time
import requests
from bs4 import BeautifulSoup

# جلب بيانات المصادقة والمستودع تلقائياً من بيئة GitHub Actions
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("GITHUB_REPOSITORY")  # مثال: ApexBuildHQ/Chief-King-2
BRANCH = "Control"

TARGET_RECIPES = 20000
CHUNK_SIZE = 100

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def get_recipe_urls():
    """توليد أو جلب روابط الوصفات المستهدفة"""
    urls = []
    for i in range(1, TARGET_RECIPES + 1):
        urls.append(f"https://www.allrecipes.com/recipe/{i}/example/")
    return urls


def extract_recipe_data(url):
    """استخراج بيانات الوصفة بدقة من وسوم JSON-LD"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        json_ld_scripts = soup.find_all("script", type="application/ld+json")

        recipe_data = None
        for script in json_ld_scripts:
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
        return structured_recipe
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return None


def push_chunk_to_github(chunk_data, chunk_index):
  """رفع الملف مباشرة إلى المستودع عبر GitHub API بدون حفظه محلياً"""
  if not GITHUB_TOKEN or not REPO_NAME:
    print("خطأ: ت Nأكد من توفر GITHUB_TOKEN و GITHUB_REPOSITORY")
    return

  file_path = f"recipe_chunks/chunk_{chunk_index}.json"
  url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"

  # تجهيز محتوى الـ JSON وترميزه بصيغة Base64 المطلوبة للـ API
  json_content = json.dumps(chunk_data, ensure_ascii=False, indent=4)
  encoded_content = base64.b64encode(json_content.encode("utf-8")).decode(
      "utf-8"
  )

  headers = {
      "Authorization": f"Bearer {GITHUB_TOKEN}",
      "Accept": "application/vnd.github+json",
  }

  # التحقق مما إذا كان الملف موجوداً مسبقاً لجلب الـ SHA الخاص به (مطلوب لعملية التحديث)
  get_resp = requests.get(url, headers=headers, params={"ref": BRANCH})
  sha = None
  if get_resp.status_code == 200:
    sha = get_resp.json().get("sha")

  payload = {
      "message": f"Add recipe chunk {chunk_index} via direct API [skip ci]",
      "content": encoded_content,
      "branch": BRANCH,
  }
  if sha:
    payload["sha"] = sha

  # إرسال طلب الرفع المباشر
  put_resp = requests.put(url, headers=headers, json=payload)
  if put_resp.status_code in [200, 201]:
    print(f"تم رفع الملف بنجاح إلى المستودع: {file_path}")
  else:
    print(f"فشل رفع الملف {file_path}: {put_resp.text}")


def main():
  urls = get_recipe_urls()
  current_chunk = []
  chunk_index = 1
  processed_count = 0

  print(
      f"بدء سحب {TARGET_RECIPES} وصفة والرفع المباشر للملفات عبر GitHub API..."
  )

  for idx, url in enumerate(urls):
    recipe = extract_recipe_data(url)
    if recipe:
      current_chunk.append(recipe)
      processed_count += 1

    # عند اكتمال 100 وصفة، يتم إرسالها فوراً للمستودع وتفريغ الذاكرة
    if len(current_chunk) == CHUNK_SIZE or (
        idx == len(urls) - 1 and current_chunk
    ):
      push_chunk_to_github(current_chunk, chunk_index)
      chunk_index += 1
      current_chunk = []

    time.sleep(1.5)  # فاصل زمني لتجنب الحظر


if __name__ == "__main__":
  main()
