# Security Checklist — Trading Bot

## API Keys

- [ ] `.env` file kabhi kisi ko share nahi karni — na screenshot, na copy-paste,
      na chat mein, na cloud storage (Google Drive, WhatsApp, email) mein
- [ ] Binance API key permissions check karo (waqtan-faqtan):
      **Spot Trading: ON, Withdrawals: OFF, Margin/Futures: OFF**
- [ ] Har 1-2 mahine keys **regenerate** karo (Gemini + Binance) — purani
      revoke kar do, naya `.env` mein daal do
- [ ] `.gitignore` file hamesha isi folder mein rakhna (agar kabhi code
      GitHub ya kisi cloud par upload karo, `.env` khud-ba-khud exclude
      ho jayegi)

## Laptop Security

- [ ] Laptop disk encryption ON karo (Windows: BitLocker,
      Settings > Privacy & Security > Device Encryption)
- [ ] Laptop par strong login password/PIN rakho
- [ ] Laptop kisi aur ko mat do bina apna account log-out kiye

## Account Isolation

- [ ] Bot ka paisa sirf **sub-account** mein rakhna — main account/savings
      alag rakhna
- [ ] Jo paisa daalo, sirf utna jiska **khona afford ho sake** — ye koi
      guaranteed-safe system nahi hai

## Monitoring (roz karna)

- [ ] Binance app khud khol kar balance/open positions check karo
- [ ] `trade_log.csv` dekho — kya trades hui, kya profit/loss raha
- [ ] Telegram alerts miss to nahi hui (VPN on hai check karo agar
      Pakistan mein ho)
- [ ] Agar koi 🚨 URGENT alert aaye, turant Binance app mein check karo

## Scaling (balance badhane se pehle)

- [ ] Chhote balance ($50-100) par kam se kam 1-2 hafte bina kisi manual
      fix ke chalna chahiye, tabhi barhao
- [ ] Ek sath poora paisa mat daalo — dheere dheere ($100 → $150 → $200...)
- [ ] Har baar balance barhane se pehle recent `trade_log.csv` dekh lo —
      koi anjaana bug to nahi hua

## Known Limitations (in par kaam ho raha hai / aage karna hai)

- Momentum-exit aur OCO ke beech "race condition" ka chhota risk
  (dono ek sath trigger hon to)
- Agar bot crash ho crash ke exact waqt, `cooldowns` state kabhi save
  na ho paye
- News aur token-unlock data abhi shamil nahi (future addition)
