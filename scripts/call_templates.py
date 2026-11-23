"""Segment variants for the synthetic labeled test calls (scripts/make_transcripts.py).

Every call is built from the same skeleton, with one variant picked per
segment. The variant names are also the labels, so the expected answers are
known without anyone reading the calls. Puentara is a fictional company.
Spanish agent lines use "tú".
"""

AGENTS = ["Dana P.", "Marco T.", "Sofía R.", "Iván L."]
CUSTOMERS = {"en": ["Alex Demo", "Jordan Sample", "Sam Placeholder", "Riley Test"],
             "es": ["Luis Muestra", "Valeria Ejemplo", "Andrés Prueba", "Paola Demo"]}

GREETING = {
    "en": "Thanks for calling Puentara, my name is {agent}. How can I help you today?",
    "es": "Gracias por llamar a Puentara, te habla {agent}. ¿En qué te puedo ayudar?",
}
NO_GREETING = {"en": "Hello?", "es": "¿Aló?"}
RECORDING = {
    "en": [" This call is recorded for quality.", " Just so you know, this call may be recorded."],
    "es": [" Esta llamada es grabada con fines de calidad.", " Te aviso que esta llamada puede ser grabada."],
}

PROBLEMS = {
    "account_access": {"en": "I can't log in to my account since yesterday.",
                       "es": "No puedo entrar a mi cuenta desde ayer."},
    "identity_verification": {"en": "The app keeps rejecting my ID photo.",
                              "es": "La app sigue rechazando la foto de mi identificación."},
    "card_lost_stolen": {"en": "I think my card was stolen at the gym today.",
                         "es": "Creo que me robaron la tarjeta hoy en el gimnasio."},
    "transfer_failed_pending": {"en": "I sent {amount} on Monday and it still says pending.",
                                "es": "Mandé {amount} el lunes y todavía sale pendiente."},
    "charge_dispute": {"en": "There's a charge for {amount} I don't recognize and I want to dispute it.",
                       "es": "Hay un cargo de {amount} que no reconozco y quiero disputarlo."},
    "fees": {"en": "Why was I charged a $4.99 fee on my transfer?",
             "es": "¿Por qué me cobraron una comisión de 4.99 dólares en mi transferencia?"},
    "tax_forms": {"en": "Where can I find my 1099 form for last year?",
                  "es": "¿Dónde encuentro mi formulario 1099 del año pasado?"},
    "app_bug": {"en": "The app freezes every time I open the transfers screen.",
                "es": "La app se congela cada vez que abro la pantalla de transferencias."},
    "general_question": {"en": "What are your support hours?",
                         "es": "¿Cuál es el horario de atención?"},
}

EMPATHY = {
    "ack": {"en": ["I'm sorry to hear that, I understand how stressful this is.",
                   "I'm sorry about that, let's sort it out together."],
            "es": ["Lamento lo que pasó, entiendo lo estresante que es.",
                   "Siento mucho la molestia, lo resolvemos juntos."]},
    "curt": {"en": ["That's not really our problem.", "Yeah, that happens."],
             "es": ["Eso no es problema nuestro.", "Sí, eso pasa."]},
}

# Verification asks. "allowed" uses factors from rubric.json; the others are
# the sensitive-data requests the rule must catch.
VERIFY = {
    "allowed": {"en": ["Before we look at your account, can you confirm your full name and date of birth?",
                       "First, can you confirm your full name and the last 4 digits of your card?",
                       "I just sent a confirmation prompt to your Puentara app. Can you tap Approve?"],
                "es": ["Antes de revisar tu cuenta, ¿me confirmas tu nombre completo y tu fecha de nacimiento?",
                       "Primero, ¿me confirmas tu nombre completo y los últimos 4 dígitos de tu tarjeta?",
                       "Te acabo de enviar una confirmación a la app de Puentara. ¿La puedes aprobar?"]},
    "full_card": {"en": ["To verify you, can you give me your full card number?",
                         "Can you read me the 16 digits on your card?"],
                  "es": ["Para verificarte, ¿me das el número completo de tu tarjeta?",
                         "¿Me dictas los 16 dígitos de tu tarjeta?"]},
    "pin": {"en": ["To verify you, what's your PIN?", "Can you tell me your card PIN?"],
            "es": ["Para verificarte, dime tu PIN.", "¿Me confirmas el PIN de tu tarjeta?"]},
    "otp": {"en": ["I just texted you a code. Can you read me the code?",
                   "What's the verification code we sent you?"],
            "es": ["Te mandé un mensaje. ¿Me lees el código que te llegó?",
                   "¿Cuál es el código de verificación que te enviamos?"]},
    "skipped": {"en": ["Let me pull up your account."], "es": ["Déjame revisar tu cuenta."]},
}
SENSITIVE_KIND = {"full_card": "card_number", "pin": "pin", "otp": "otp"}

CUSTOMER_ANSWER = {
    "allowed": {"en": "Sure, it's {name}.", "es": "Claro, soy {name}."},
    "sensitive": {"en": "Um, I'm not sure I should share that.", "es": "Mmm, no sé si debo compartir eso."},
    "skipped": {"en": "Okay.", "es": "Ok."},
    # Trap: the customer volunteers a (fake) card number. Masked, and never the agent's fault.
    "volunteer": {"en": "Sure, it's {name}. And my card number is {card}, in case you need it.",
                  "es": "Claro, soy {name}. Y mi tarjeta es {card}, por si la necesitas."},
}

ACCOUNT_LINE = {"en": "Thanks. I can see your account now.", "es": "Gracias. Ya veo tu cuenta."}
# Trap: an agent saying the right thing about PINs must NOT be flagged.
NEVER_ASK = {"en": " Just so you know, we will never ask for your PIN or password.",
             "es": " Te cuento que nunca te vamos a pedir tu PIN ni tu contraseña."}

CUSTOMER_FOLLOWUP = {"en": "So what happens now?", "es": "¿Y ahora qué pasa?"}

NEXT_STEP = {
    "account_access": {"en": "I'm sending a reset link to your registered email",
                       "es": "te envío un enlace para restablecer el acceso a tu correo registrado"},
    "identity_verification": {"en": "I'm sending your ID photo to our verification team",
                              "es": "envío la foto de tu identificación al equipo de verificación"},
    "transfer_failed_pending": {"en": "I'm asking the payments team to review the transfer",
                                "es": "le pido al equipo de pagos que revise la transferencia"},
    "fees": {"en": "I'm sending you the fee table by email",
             "es": "te envío la tabla de comisiones por correo"},
    "tax_forms": {"en": "your 1099 is in the app under Documents",
                  "es": "tu formulario 1099 está en la app, en Documentos"},
    "app_bug": {"en": "I'm reporting the freeze to our tech team",
                "es": "reporto el congelamiento al equipo técnico"},
    "general_question": {"en": "our phone line is open from 8 a.m. to 8 p.m. Eastern time",
                         "es": "la línea atiende de 8 a. m. a 8 p. m., hora del este"},
}
RESOLUTION = {
    "next_steps": {
        "default": {"en": "Here's what happens next: {step}. You'll get an update within 3 business days. Does that make sense?",
                    "es": "Esto es lo que sigue: {step}. Te llega una actualización en 3 días hábiles. ¿Te queda claro?"},
        "charge_dispute": {"en": "I've opened a dispute. Our team reviews it within 10 business days and you'll get an email with the result. Does that make sense?",
                           "es": "Ya abrí la disputa. El equipo la revisa en un plazo de 10 días hábiles y te llega un correo con el resultado. ¿Te queda claro?"},
        "card_lost_stolen": {"en": "I've frozen the card and I'm transferring you to our security team to review recent activity and send a replacement. Does that make sense?",
                             "es": "Ya congelé la tarjeta y te transfiero con el equipo de seguridad para revisar los movimientos y enviarte una nueva. ¿Te queda claro?"},
    },
    "vague": {"en": "We'll look into it at some point.", "es": "Lo vamos a revisar en algún momento."},
    # Disputes only: promising an outcome is flagged by the rules.
    "promise": {"en": "Don't worry, you'll definitely get your money back.",
                "es": "Tranquilo, seguro te devolvemos el dinero."},
}
CUSTOMER_THANKS = {"en": "Okay, thanks.", "es": "Ok, gracias."}
CLOSING = {"en": "Thanks for calling Puentara.", "es": "Gracias por llamar a Puentara."}
