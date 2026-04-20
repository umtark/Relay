def selamla(isim="Ümit Arik"):
    asistan = "Relay"
    yaratıcı = "Ümit Arik"

    if isim == "Ahmet":
        mesaj = f"Selam Ahmet! Ümit Bey seni buralarda görmekten memnun olur."
    else:
        mesaj = f"Merhaba Ümit Bey! Ben {asistan}. Senin için her zaman buradayım."

    print("-" * len(mesaj))
    print(mesaj)
    print("-" * len(mesaj))

if __name__ == "__main__":
    selamla()