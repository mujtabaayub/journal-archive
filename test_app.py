import streamlit as st

st.title("Widget test")

x = st.slider("Slider", 0, 10, 5)
st.write(f"Slider value: {x}")

opts = ["apple", "banana", "cherry"]
sel = st.multiselect("Multiselect", opts, default=opts)
st.write(f"Selected: {sel}")

q = st.text_input("Text input")
st.write(f"Typed: {q}")
