from dotenv import load_dotenv
load_dotenv()  # must run before any app imports read os.environ

from app.bot.trader import run

if __name__ == "__main__":
    run()
