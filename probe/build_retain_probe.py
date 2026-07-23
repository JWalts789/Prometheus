"""Author the RETAIN probe: a broad, factually-correct general-knowledge test used every
cycle to detect catastrophic forgetting. Short, gradeable answers + aliases. Curated by hand
(NOT model-generated) so the yardstick itself is never wrong. Run: python probe/build_retain_probe.py
"""
import json
from pathlib import Path

# (question, canonical answer, [aliases])
ITEMS = [
    # --- Geography ---
    ("What is the capital of France?", "Paris", []),
    ("What is the capital of Japan?", "Tokyo", []),
    ("What is the capital of Australia?", "Canberra", []),
    ("What is the capital of Canada?", "Ottawa", []),
    ("What is the capital of Egypt?", "Cairo", []),
    ("What is the capital of Brazil?", "Brasilia", []),
    ("What is the largest ocean on Earth?", "Pacific", ["Pacific Ocean"]),
    ("What is the longest river in the world?", "Nile", ["Nile River", "the Amazon"]),
    ("What is the tallest mountain on Earth?", "Mount Everest", ["Everest"]),
    ("On which continent is the Sahara Desert?", "Africa", []),
    ("Which country has the largest population?", "India", []),
    ("What is the smallest country in the world?", "Vatican City", ["the Vatican"]),
    ("Which desert is the largest hot desert on Earth?", "Sahara", ["the Sahara"]),
    ("What is the capital of Germany?", "Berlin", []),
    ("What is the capital of Russia?", "Moscow", []),
    # --- Science: biology ---
    ("What organelle is the powerhouse of the cell?", "Mitochondria", ["mitochondrion"]),
    ("What gas do plants absorb for photosynthesis?", "Carbon dioxide", ["CO2"]),
    ("What gas do plants release during photosynthesis?", "Oxygen", ["O2"]),
    ("What molecule carries genetic information?", "DNA", ["deoxyribonucleic acid"]),
    ("How many chambers does the human heart have?", "Four", []),
    ("What is the largest organ of the human body?", "Skin", ["the skin"]),
    ("What blood cells carry oxygen?", "Red blood cells", ["erythrocytes"]),
    ("What process do plants use to make food from light?", "Photosynthesis", []),
    ("What is the basic unit of life?", "The cell", ["cell"]),
    ("What part of the plant conducts photosynthesis?", "Leaves", ["the leaf", "leaf"]),
    ("Humans have how many pairs of chromosomes?", "23", ["twenty-three"]),
    ("What vitamin does sunlight help the body produce?", "Vitamin D", []),
    # --- Science: chemistry / physics ---
    ("What is the chemical symbol for gold?", "Au", []),
    ("What is the chemical symbol for oxygen?", "O", []),
    ("What is the chemical symbol for sodium?", "Na", []),
    ("What is the chemical formula for water?", "H2O", []),
    ("What is the most abundant gas in Earth's atmosphere?", "Nitrogen", ["N2"]),
    ("What is the atomic number of hydrogen?", "1", ["one"]),
    ("Approximately how fast does light travel in a vacuum?", "300000 km/s", ["299792 km/s", "3x10^8 m/s"]),
    ("What force pulls objects toward the Earth?", "Gravity", []),
    ("What is the freezing point of water in Celsius?", "0 degrees", ["zero", "0"]),
    ("What is the boiling point of water in Celsius at sea level?", "100 degrees", ["100"]),
    ("What particle has a negative electric charge?", "Electron", []),
    ("What is the hardest known natural material?", "Diamond", []),
    ("What planet is known as the Red Planet?", "Mars", []),
    ("What is the largest planet in the solar system?", "Jupiter", []),
    ("What star is at the center of our solar system?", "The Sun", ["Sun", "Sol"]),
    # --- Mathematics / logic / reasoning ---
    ("What is 7 times 8?", "56", ["fifty-six"]),
    ("What is 12 times 12?", "144", []),
    ("What is 15 percent of 200?", "30", ["thirty"]),
    ("What is the square root of 81?", "9", ["nine"]),
    ("What is the value of pi to two decimal places?", "3.14", []),
    ("How many sides does a hexagon have?", "6", ["six"]),
    ("How many degrees are in a right angle?", "90 degrees", ["90"]),
    ("What is the next prime number after 7?", "11", ["eleven"]),
    ("If a shirt costs $20 and is 25% off, what is the sale price?", "15 dollars", ["$15", "15"]),
    ("What is one half plus one quarter?", "three quarters", ["3/4", "0.75"]),
    ("How many degrees are in a triangle's interior angles?", "180 degrees", ["180"]),
    ("What is 100 divided by 4?", "25", ["twenty-five"]),
    # --- History ---
    ("In what year did World War II end?", "1945", []),
    ("Who was the first President of the United States?", "George Washington", ["Washington"]),
    ("What ancient civilization built the pyramids at Giza?", "Ancient Egypt", ["Egyptians", "Egypt"]),
    ("Who wrote the Declaration of Independence's first draft?", "Thomas Jefferson", ["Jefferson"]),
    ("What wall fell in 1989 dividing a German city?", "Berlin Wall", ["the Berlin Wall"]),
    ("Who was the British Prime Minister during most of WWII?", "Winston Churchill", ["Churchill"]),
    ("In what year did the Titanic sink?", "1912", []),
    ("What empire was ruled by Julius Caesar?", "Roman Empire", ["Rome", "the Romans"]),
    ("Who led India's nonviolent independence movement?", "Mahatma Gandhi", ["Gandhi"]),
    ("What year did the American Civil War begin?", "1861", []),
    ("Who was the leader of Nazi Germany?", "Adolf Hitler", ["Hitler"]),
    ("What document begins with 'We the People'?", "The US Constitution", ["Constitution"]),
    # --- Language / vocabulary / grammar ---
    ("What is the opposite of 'ancient'?", "Modern", ["new", "recent"]),
    ("What is a synonym for 'happy'?", "Joyful", ["glad", "cheerful", "content"]),
    ("What is the plural of 'mouse' (the animal)?", "Mice", []),
    ("What part of speech describes an action?", "Verb", []),
    ("What is the past tense of 'go'?", "Went", []),
    ("What is the opposite of 'expand'?", "Contract", ["shrink"]),
    ("A word that describes a noun is called what?", "Adjective", []),
    ("What is a synonym for 'begin'?", "Start", ["commence", "initiate"]),
    ("What punctuation ends a question?", "Question mark", []),
    ("What is the antonym of 'generous'?", "Stingy", ["selfish", "miserly"]),
    # --- Arts / literature / music / culture ---
    ("Who painted the Mona Lisa?", "Leonardo da Vinci", ["da Vinci", "Leonardo"]),
    ("Who wrote the play 'Romeo and Juliet'?", "William Shakespeare", ["Shakespeare"]),
    ("How many strings does a standard guitar have?", "6", ["six"]),
    ("Who composed the Ninth Symphony with 'Ode to Joy'?", "Beethoven", ["Ludwig van Beethoven"]),
    ("What novel features the character Sherlock Holmes's creator?", "Arthur Conan Doyle", ["Conan Doyle"]),
    ("What are the three primary colors of light?", "Red, green, blue", ["RGB"]),
    ("Who wrote 'War and Peace'?", "Leo Tolstoy", ["Tolstoy"]),
    ("What instrument has 88 keys?", "Piano", ["the piano"]),
    ("In which country did the Renaissance begin?", "Italy", []),
    ("Who directed the film 'Jaws' and 'E.T.'?", "Steven Spielberg", ["Spielberg"]),
    # --- Everyday knowledge / common sense / instruction-following ---
    ("How many days are in a leap year?", "366", []),
    ("How many minutes are in an hour?", "60", ["sixty"]),
    ("How many continents are there on Earth?", "7", ["seven"]),
    ("What is the freezing point of water in Fahrenheit?", "32 degrees", ["32"]),
    ("How many colors are in a rainbow?", "7", ["seven"]),
    ("What do bees collect from flowers to make honey?", "Nectar", []),
    ("What is the main gas that makes up the Sun?", "Hydrogen", []),
    ("What organ pumps blood through the body?", "The heart", ["heart"]),
    ("Name the season that comes after winter.", "Spring", []),
    ("What do you call frozen water?", "Ice", []),
    ("How many legs does a spider have?", "8", ["eight"]),
    ("What is the largest mammal on Earth?", "Blue whale", ["the blue whale"]),
    ("Spell the word 'necessary'.", "necessary", []),
    ("What is the first month of the year?", "January", []),
    ("Complete the phrase: the early bird catches the ...", "worm", ["the worm"]),
    ("What color do you get mixing blue and yellow paint?", "Green", []),
    ("How many sides does a triangle have?", "3", ["three"]),
    ("What planet do we live on?", "Earth", []),
    ("What is the currency used in the United States?", "Dollar", ["US dollar", "dollars"]),
    ("How many letters are in the English alphabet?", "26", ["twenty-six"]),
]


def main():
    out = Path(__file__).resolve().parent / "retain_probe.jsonl"
    if out.exists():
        bak = out.with_suffix(".jsonl.bak")
        bak.write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"backed up old retain probe -> {bak.name}")
    seen, rows = set(), []
    for q, a, al in ITEMS:
        if q in seen:
            continue
        seen.add(q)
        rows.append({"q": q, "a": a, "aliases": al})
    with open(out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} retain items -> {out}")


if __name__ == "__main__":
    main()
