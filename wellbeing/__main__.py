from wellbeing.app import main

# The guard matters: worker processes import this module again on start-up.
if __name__ == "__main__":
    raise SystemExit(main())
