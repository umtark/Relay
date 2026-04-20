def selamla(isim="Ümit Arik"):
    asistan = "Relay"
    yaratıcı = "Ümit Arik"

    if isim == "Samet":
        mesaj = f"Selam Samet! Ümit Bey seni buralarda görmekten memnun olur."
    else:
        mesaj = f"Merhaba Ümit Bey! Ben {asistan}. Sizin için her zaman buradayım."

    print("-" * len(mesaj))
    print(mesaj)
    print("-" * len(mesaj))
    print(f"Sistem Durumu: {yaratıcı} tarafından başarıyla yapılandırıldı.")

if __name__ == "__main__":
    selamla()