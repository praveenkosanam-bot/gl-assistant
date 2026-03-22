Run Rasa separately if you want model-based intent parsing.

Typical flow:
1. Install Rasa in a separate environment.
2. Train from this folder:
   `rasa train`
3. Start the Rasa API server:
   `rasa run --enable-api --cors "*"`
4. Set `RASA_URL=http://127.0.0.1:5005` in the app environment.

When `RASA_URL` is configured, the Flask app will call `POST /model/parse` on the Rasa server.
If Rasa is unavailable, the app falls back to the built-in lightweight parser.
