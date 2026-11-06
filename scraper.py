import json
import os
import time
import requests
from bs4 import BeautifulSoup

# إعدادات المجلدات وتخزين الملفات
OUTPUT_DIR = "recipe_chunks"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHUNK_SIZE = 100
TARGET_RECIPES = 20000

# رأس الطلب لمحاكاة متصفح حقيقي وتفادي الحظر الأولي
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def get_recipe_urls():
    """دالة لجلب أو توليد قائمة روابط الوصفات المستهدفة (20 ألف رابط)

    (يمكن استبدالها بقراءة سبيكة روابط من ملف sitemap أو قاعدة بيانات)
    """
    # مثال توضيحي لهيكل الروابط؛ في الواقع العملي يتم جلبها من ملف Sitemap الخاص بالموقع
    # هنا نفترض وجود قائمة روابط جاهزة أو آلية توليد لروابط الوصفات
    urls = []
    # مثال افتراضي لطريقة جلب الروابط (يتم تعديلها حسب مصدر الروابط الفعلي)
    for i in range(1, TARGET_RECIPES + 1):
        # استبدال هذا الرابط بنمط روابط الموقع المستهدف (مثل Allrecipes)
        urls.append(f"https://www.allrecipes.com/recipe/{i}/example/")
    return urls


def extract_recipe_data(url):
    """استخراج بيانات الوصفة بدقة من وسوم JSON-LD"""
    try:
        response = requests.get(
            url, headers=HEADERS, timeout=15
        )
        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")
        json_ld_scripts = soup.find_all(
            "script", type="application/ld+json"
        )

        recipe_data = None
        for script in json_ld_scripts:
            try:
                data = json.loads(script.string)
                # قد يكون الـ JSON على شكل قائمة أو كائن مباشر
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

    # هيكلة البيانات المطلوبة بدقة عالية تطابق معايير السيو
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


def main():
    urls = get_recipe_urls()
    current_chunk = []
    chunk_index = 1
    processed_count = 0

    print(
        f"بدء عملية سحب {TARGET_RECIPES} وصفة وتقسيمها إلى دفعات (كل 100 وصفة في"
        " ملف)..."
    )

    for idx, url in enumerate(urls):
        recipe = extract_recipe_data(url)

        if recipe:
            current_chunk.append(recipe)
            processed_count += 1

        # حفظ الملف عند اكتمال 100 وصفة أو الوصول للنهاية
        if len(current_chunk) == CHUNK_SIZE or (
            idx == len(urls) - 1 and current_chunk
        ):
            file_name = os.path.join(
                OUTPUT_DIR, f"chunk_{chunk_index}.json"
            )
            with open(file_name, "w", encoding="utf-8") as f:
                json.dump(current_chunk, f, ensure_ascii=False, indent=4)

            print(
                f"تم حفظ الملف بنجاح: chunk_{chunk_index}.json (إجمالي"
                f" الوصفات المسحوبة: {processed_count})"
            )

            chunk_index += 1
            current_chunk = []

        # فاصل زمني عشوائي أو منتظم لمنع الحظر (Rate Limiting)
        time.sleep(2)


if __name__ == "__main__":
    main()
