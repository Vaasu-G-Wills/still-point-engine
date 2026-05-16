import streamlit as st
from pipeline import run_pipeline
from db import get_all_scripts, delete_script
from tts_engine import AVAILABLE_VOICES
import json
import os

st.set_page_config(page_title="Still Point Engine", layout="wide", page_icon="⚙️")

st.title("The Still Point Script Engine")
st.markdown("Automated Dialectic Multi-Agent Pipeline with Reverse-RAG")

tab1, tab2, tab3 = st.tabs(["⚡ Generator", "📚 Script Library", "🔥 Trending Topics"])

# ─────────────────────────────────────────────────────────────
# PHASE STATE — persists across Streamlit reruns
# ─────────────────────────────────────────────────────────────
if "output_data"    not in st.session_state: st.session_state.output_data    = None
if "phase"          not in st.session_state: st.session_state.phase          = 1
if "tts_voice_used" not in st.session_state: st.session_state.tts_voice_used = None
if "yt_metadata"    not in st.session_state: st.session_state.yt_metadata    = None
if "yt_result"      not in st.session_state: st.session_state.yt_result      = None
if "trend_results"  not in st.session_state: st.session_state.trend_results  = None
if "prefill_topic"  not in st.session_state: st.session_state.prefill_topic  = ""

with tab1:

    # ─── PHASE 1: Script & Audio Generation ──────────────────
    if st.session_state.phase == 1:
        col_input, col_voice = st.columns([3, 1])
        with col_input:
            topic_input = st.text_input(
                "Enter Topic",
                value=st.session_state.prefill_topic,
                placeholder="e.g. The commodification of education",
                key="topic_text_input"
            )
            # Clear prefill after it's been loaded so it doesn't persist forever
            if st.session_state.prefill_topic and topic_input:
                st.session_state.prefill_topic = ""
        with col_voice:
            selected_voice = st.selectbox("TTS Voice", options=["None"] + AVAILABLE_VOICES)

        word_by_word = st.checkbox("💬 Word-by-Word Subtitles in video (DaVinci style, CPU only)", value=True)
        st.session_state.word_by_word = word_by_word

        generate_btn = st.button("⚡ Generate Script & Audio", type="primary")

        if generate_btn and topic_input:
            status_placeholder = st.empty()
            exclusions_placeholder = st.empty()

            col1, col2, col3 = st.columns(3)
            with col1:
                st.subheader("Node A: Thesis")
                thesis_box = st.empty()
            with col2:
                st.subheader("Node B: Antithesis")
                anti_box = st.empty()
            with col3:
                st.subheader("Node C: Synthesis")
                synth_box = st.empty()

            def ui_callback(event, data):
                if event == "status":
                    status_placeholder.info(data)
                elif event == "exclusions":
                    with exclusions_placeholder.expander("Reverse-RAG Active: Excluded Arguments", expanded=True):
                        for ex in data:
                            st.warning(ex)
                elif event == "hook":
                    with col1:
                        st.markdown("**🎯 Hook**")
                        st.info(data)
                elif event == "thesis":
                    thesis_box.markdown(data)
                elif event == "bridge_ab":
                    with col2:
                        st.markdown("**🔗 Bridge**")
                        st.info(data)
                elif event == "antithesis":
                    anti_box.markdown(data)
                elif event == "bridge_bc":
                    with col3:
                        st.markdown("**🔗 Bridge**")
                        st.info(data)
                elif event == "synthesis":
                    synth_box.markdown(data)

            try:
                tts_param = None if selected_voice == "None" else selected_voice
                output = run_pipeline(
                    topic_input,
                    yield_callback=ui_callback,
                    tts_voice=tts_param,
                    render_video=False,   # Video is Phase 2
                )
                st.session_state.output_data    = output
                st.session_state.tts_voice_used = tts_param
                st.session_state.phase          = 2
                status_placeholder.success(
                    f"✅ Script & Audio complete! ({output['word_count']} words) — "
                    "Scroll down to upload images and render your video."
                )
                st.rerun()

            except Exception as e:
                st.error(f"Error during generation: {e}")

    # ─── PHASE 2: Image Upload & Video Render ────────────────
    elif st.session_state.phase == 2:
        output = st.session_state.output_data
        sections = output.get("sections", {})
        topic_dir = output.get("folder_path", "")
        audio_dir = os.path.join(topic_dir, "audio")

        st.success(f"✅ Script ready: **{output['topic']}** ({output['word_count']} words)")

        if st.button("← Start a new script", type="secondary"):
            st.session_state.phase = 1
            st.session_state.output_data = None
            st.rerun()

        st.divider()

        # ── Show the full final script ────────────────────────
        with st.expander("📄 View Full Script", expanded=True):
            for label, key in [
                ("🎯 Hook",        "hook"),
                ("📖 Thesis",      "thesis"),
                ("🔗 Bridge",      "bridge_ab"),
                ("⚡ Antithesis",  "antithesis"),
                ("🔗 Bridge",      "bridge_bc"),
                ("⚖️ Synthesis",   "synthesis"),
            ]:
                text = sections.get(key, "")
                if text:
                    st.markdown(f"**{label}**")
                    st.markdown(text)
                    st.markdown("")

        # ── Playback Generated Audio ──────────────────────────
        if os.path.exists(audio_dir):
            st.markdown("### 🎙️ Generated Audio")
            a1, a2, a3 = st.columns(3)
            with a1:
                for seg in ["hook", "thesis"]:
                    p = os.path.join(audio_dir, f"{seg}.wav")
                    if os.path.exists(p):
                        st.caption(seg.capitalize())
                        st.audio(p)
            with a2:
                for seg in ["bridge_ab", "antithesis"]:
                    p = os.path.join(audio_dir, f"{seg}.wav")
                    if os.path.exists(p):
                        st.caption(seg.replace("_", " → ").capitalize())
                        st.audio(p)
            with a3:
                for seg in ["bridge_bc", "synthesis"]:
                    p = os.path.join(audio_dir, f"{seg}.wav")
                    if os.path.exists(p):
                        st.caption(seg.replace("_", " → ").capitalize())
                        st.audio(p)

        st.divider()

        # ── Phase 2: Upload Images → Render Video ─────────────
        st.markdown("### 🎬 Step 2 — Upload Backgrounds & Render Video")
        st.info(
            "Read your final script above, generate or source your background images, "
            "then upload them below. Each section will use its own visual."
        )

        tts_ok = st.session_state.tts_voice_used is not None
        if not tts_ok:
            st.warning("⚠️ No TTS voice was used — video cannot be rendered without audio. Regenerate with a voice selected.")
        else:
            p1, p2, p3 = st.columns(3)
            with p1:
                st.markdown("**Thesis section**")
                st.caption(sections.get("thesis", "")[:200] + "...")
                bg_thesis = st.file_uploader("Thesis Background", type=["png","jpg","jpeg"], key="v_thesis")
            with p2:
                st.markdown("**Antithesis section**")
                st.caption(sections.get("antithesis", "")[:200] + "...")
                bg_anti   = st.file_uploader("Antithesis Background", type=["png","jpg","jpeg"], key="v_anti")
            with p3:
                st.markdown("**Synthesis section**")
                st.caption(sections.get("synthesis", "")[:200] + "...")
                bg_synth  = st.file_uploader("Synthesis Background", type=["png","jpg","jpeg"], key="v_synth")

            word_by_word = st.session_state.get("word_by_word", True)
            render_btn = st.button("🎬 Render Master Video", type="primary")

            if render_btn:
                import video_engine

                # Save uploaded images to topic_dir
                bg_paths = {}
                for node_key, uploaded_file in [("thesis", bg_thesis), ("antithesis", bg_anti), ("synthesis", bg_synth)]:
                    if uploaded_file:
                        bpath = os.path.join(topic_dir, f"bg_{node_key}.jpg")
                        with open(bpath, "wb") as f:
                            f.write(uploaded_file.read())
                        bg_paths[node_key] = bpath

                render_status = st.empty()
                progress_bar  = st.progress(0)

                def on_progress(current, total, message):
                    render_status.info(message)
                    if total > 0:
                        progress_bar.progress(min(current / total, 1.0))

                try:
                    video_engine.ensure_font()
                    out_path = video_engine.build_master_video(
                        topic_dir, output,
                        bg_images=bg_paths,
                        word_by_word=word_by_word,
                        progress_callback=on_progress
                    )
                    progress_bar.progress(1.0)
                    render_status.success("✅ Video rendered successfully!")
                    st.video(out_path)
                except Exception as ve:
                    render_status.error(f"Video rendering failed: {ve}")

        # ── Show existing video if already rendered ─────────────
        video_path = os.path.join(topic_dir, "master_video.mp4")
        if os.path.exists(video_path):
            st.markdown("### 🏞️ Previously Rendered Video")
            st.video(video_path)

        # ───────────────────────────────────────────────────────
        # PHASE 3: YouTube Publisher
        # ───────────────────────────────────────────────────────
        video_path = os.path.join(topic_dir, "master_video.mp4")
        if os.path.exists(video_path):
            st.divider()
            st.markdown("### 📤 Step 3 — Publish to YouTube")

            if not os.path.exists("client_secret.json"):
                st.error("🔐 `client_secret.json` not found. Download OAuth credentials from Google Cloud Console and place them in the project directory.")
            else:
                # ── Research Metadata ──────────────────────────
                if st.button("🔍 Research YouTube Metadata (Title, Tags, Description)", type="secondary"):
                    with st.spinner("🧠 LLM is crafting metadata + researching ranking tags..."):
                        try:
                            from yt_research import generate_yt_metadata
                            meta = generate_yt_metadata(output["topic"], output)
                            st.session_state.yt_metadata = meta
                        except Exception as e:
                            st.error(f"Metadata research failed: {e}")

                meta = st.session_state.yt_metadata
                if meta:
                    st.success("✅ Metadata ready — review and edit before uploading.")

                    yt_title = st.text_input(
                        "📝 Title",
                        value=meta.get("title", ""),
                        max_chars=100,
                        key="yt_title_input"
                    )
                    yt_desc = st.text_area(
                        "📝 Description",
                        value=meta.get("description", ""),
                        height=180,
                        key="yt_desc_input"
                    )
                    raw_tags  = ", ".join(meta.get("tags", []))
                    yt_tags_s = st.text_input(
                        "🏷️ Tags (comma-separated)",
                        value=raw_tags,
                        key="yt_tags_input"
                    )

                    priv_col, playlist_col = st.columns(2)
                    with priv_col:
                        yt_privacy = st.selectbox(
                            "🔒 Privacy",
                            ["private", "unlisted", "public"],
                            index=0,
                            key="yt_privacy_sel"
                        )
                    with playlist_col:
                        yt_playlist = st.text_input(
                            "💼 Playlist ID (optional)",
                            placeholder="e.g. PLxxxxxxxxxxxxxx",
                            key="yt_playlist_input"
                        )

                    st.markdown("**🖼️ Thumbnail** (1280×720 recommended, max 2MB)")
                    thumbnail_file = st.file_uploader(
                        "Upload Thumbnail",
                        type=["jpg", "jpeg", "png"],
                        key="yt_thumbnail"
                    )

                    if thumbnail_file:
                        st.image(thumbnail_file, caption="Thumbnail Preview", use_container_width=False, width=320)

                    st.markdown("---")
                    # ── Category & Language ──────────────────────────────────
                    cat_col, lang_col = st.columns(2)
                    with cat_col:
                        cat_name = meta.get("category_name", "Education")
                        cat_id   = meta.get("category_id", "27")
                        st.info(f"🏷️ **Category (AI-selected):** {cat_name} (`{cat_id}`)")
                    with lang_col:
                        st.info("🇬🇧 **Language:** English (`en`) — set on both content + audio track")

                    # ── HDD Archive Path ─────────────────────────────────────
                    hdd_path = st.text_input(
                        "💾 HDD Archive Path (move folder here after upload)",
                        placeholder="e.g. /media/vaasu/MyHDD  or  /mnt/hdd",
                        help="The topic folder will be moved to <path>/Stillpoint Uploaded Videos/ after a successful upload.",
                        key="yt_hdd_path"
                    )

                    st.markdown("")
                    upload_btn = st.button("🚀 Upload to YouTube", type="primary", key="yt_upload_btn")

                    if upload_btn:
                        if not yt_title.strip():
                            st.error("Title cannot be empty.")
                        else:
                            yt_tags_list = [t.strip() for t in yt_tags_s.split(",") if t.strip()]

                            # Save thumbnail to disk
                            thumb_path = None
                            if thumbnail_file:
                                thumb_path = os.path.join(topic_dir, "thumbnail.jpg")
                                with open(thumb_path, "wb") as f:
                                    f.write(thumbnail_file.read())

                            upload_status = st.empty()
                            upload_bar    = st.progress(0)

                            def on_upload_progress(sent, total):
                                if total > 0:
                                    upload_bar.progress(min(sent / total, 1.0))
                                    mb_sent  = sent  / 1_048_576
                                    mb_total = total / 1_048_576
                                    upload_status.info(f"📤 Uploading... {mb_sent:.1f} MB / {mb_total:.1f} MB")

                            try:
                                upload_status.info("🔐 Authenticating with Google... (a browser tab may open on first use)")
                                from yt_uploader import upload_video, upload_thumbnail, move_to_archive

                                result = upload_video(
                                    video_path=video_path,
                                    title=yt_title,
                                    description=yt_desc,
                                    tags=yt_tags_list,
                                    category_id=meta.get("category_id", "27"),
                                    privacy=yt_privacy,
                                    language=meta.get("language", "en"),
                                    playlist_id=yt_playlist.strip() or None,
                                    progress_callback=on_upload_progress,
                                )

                                if thumb_path:
                                    upload_status.info("🖼️ Setting thumbnail...")
                                    upload_thumbnail(result["video_id"], thumb_path)

                                upload_bar.progress(1.0)
                                st.session_state.yt_result = result
                                upload_status.success(f"✅ Uploaded! Video is **{yt_privacy}** on YouTube.")
                                st.markdown(f"### 🎉 YouTube Link\n[{yt_title}]({result['url']})")
                                st.code(result['url'])

                                # ── Move to HDD archive ─────────────────────
                                if hdd_path and hdd_path.strip() and os.path.isdir(hdd_path.strip()):
                                    try:
                                        new_path = move_to_archive(topic_dir, hdd_path.strip())
                                        st.success(f"💾 Folder moved to: `{new_path}`")
                                        # Update session so 'Previously rendered' doesn't show stale paths
                                        st.session_state.output_data["folder_path"] = new_path
                                    except Exception as mv_err:
                                        st.warning(f"⚠️ Upload succeeded but folder move failed: {mv_err}")
                                elif hdd_path and hdd_path.strip():
                                    st.warning(f"⚠️ HDD path `{hdd_path.strip()}` not found or not mounted. Folder not moved.")

                            except FileNotFoundError as e:
                                upload_status.error(str(e))
                            except Exception as e:
                                upload_status.error(f"Upload failed: {e}")

                # Show previous upload result if it exists
                if st.session_state.yt_result:
                    prev = st.session_state.yt_result
                    st.info(f"📤 Last upload: [{prev['url']}]({prev['url']}) — **{prev['privacy']}**")

# ─────────────────────────────────────────────────────────────
# TAB 2: Script Library
# ─────────────────────────────────────────────────────────────
with tab2:
    st.header("Saved Scripts")
    scripts = get_all_scripts()

    if not scripts:
        st.info("No scripts generated yet. Go to the Generator tab to create one.")
    else:
        for s in scripts:
            with st.expander(f"{s['topic']} — {s['date']}"):
                col_btn, col_content = st.columns([1, 5])
                with col_btn:
                    if st.button("❌ Delete", key=f"del_{s['id']}"):
                        delete_script(s['id'])
                        st.rerun()

                with col_content:
                    try:
                        with open(s['file_path'], 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        st.markdown(f"**Word Count:** {data.get('word_count', 'N/A')}")

                        topic_dir_lib = os.path.dirname(s['file_path'])
                        audio_dir_lib = os.path.join(topic_dir_lib, "audio")

                        if os.path.exists(audio_dir_lib):
                            st.markdown("#### 🎙️ Audio")
                            for node in ["hook", "thesis", "bridge_ab", "antithesis", "bridge_bc", "synthesis"]:
                                wav_path = os.path.join(audio_dir_lib, f"{node}.wav")
                                if os.path.exists(wav_path):
                                    st.caption(node.replace("_", " → ").capitalize())
                                    st.audio(wav_path)

                        video_path = os.path.join(topic_dir_lib, "master_video.mp4")
                        if os.path.exists(video_path):
                            st.markdown("#### 🎬 Master Video")
                            st.video(video_path)

                            # ── YouTube Upload Panel ───────────────────────
                            st.markdown("#### 📤 Publish to YouTube")
                            if not os.path.exists("client_secret.json"):
                                st.warning("🔐 `client_secret.json` missing — add it to enable YouTube upload.")
                            else:
                                meta_key   = f"lib_yt_meta_{s['id']}"
                                result_key = f"lib_yt_result_{s['id']}"
                                if meta_key   not in st.session_state: st.session_state[meta_key]   = None
                                if result_key not in st.session_state: st.session_state[result_key] = None

                                if st.button("🔍 Research Metadata", key=f"lib_research_{s['id']}", type="secondary"):
                                    with st.spinner("🧠 Researching tags and crafting metadata..."):
                                        try:
                                            from yt_research import generate_yt_metadata
                                            st.session_state[meta_key] = generate_yt_metadata(data["topic"], data)
                                        except Exception as e:
                                            st.error(f"Metadata research failed: {e}")

                                lib_meta = st.session_state[meta_key]
                                if lib_meta:
                                    st.success("✅ Metadata ready — edit and upload.")

                                    lib_title = st.text_input(
                                        "📝 Title", value=lib_meta.get("title", ""),
                                        max_chars=100, key=f"lib_title_{s['id']}"
                                    )
                                    lib_desc = st.text_area(
                                        "📝 Description", value=lib_meta.get("description", ""),
                                        height=140, key=f"lib_desc_{s['id']}"
                                    )
                                    lib_tags_s = st.text_input(
                                        "🏷️ Tags (comma-separated)",
                                        value=", ".join(lib_meta.get("tags", [])),
                                        key=f"lib_tags_{s['id']}"
                                    )
                                    lp1, lp2 = st.columns(2)
                                    with lp1:
                                        lib_privacy = st.selectbox(
                                            "🔒 Privacy", ["private", "unlisted", "public"],
                                            index=0, key=f"lib_priv_{s['id']}"
                                        )
                                    with lp2:
                                        lib_playlist = st.text_input(
                                            "💼 Playlist ID (optional)",
                                            placeholder="PLxxxxxxxxxxxxxx",
                                            key=f"lib_playlist_{s['id']}"
                                        )

                                    lib_thumb = st.file_uploader(
                                        "🖼️ Thumbnail (1280×720, max 2MB)",
                                        type=["jpg", "jpeg", "png"],
                                        key=f"lib_thumb_{s['id']}"
                                    )
                                    if lib_thumb:
                                        st.image(lib_thumb, caption="Thumbnail Preview", width=280)

                                    st.markdown("---")
                                    lc1, lc2 = st.columns(2)
                                    with lc1:
                                        cname = lib_meta.get("category_name", "Education")
                                        cid   = lib_meta.get("category_id", "27")
                                        st.info(f"🏷️ **Category:** {cname} (`{cid}`)")
                                    with lc2:
                                        st.info("🇬🇧 **Language:** English (`en`)")

                                    lib_hdd = st.text_input(
                                        "💾 HDD Archive Path",
                                        placeholder="/media/vaasu/MyHDD",
                                        key=f"lib_hdd_{s['id']}"
                                    )

                                    if st.button("🚀 Upload to YouTube", type="primary", key=f"lib_upload_{s['id']}"):
                                        if not lib_title.strip():
                                            st.error("Title cannot be empty.")
                                        else:
                                            lib_tags_list = [t.strip() for t in lib_tags_s.split(",") if t.strip()]
                                            thumb_path = None
                                            if lib_thumb:
                                                thumb_path = os.path.join(topic_dir_lib, "thumbnail.jpg")
                                                with open(thumb_path, "wb") as f:
                                                    f.write(lib_thumb.read())

                                            up_status = st.empty()
                                            up_bar    = st.progress(0)

                                            def lib_on_progress(sent, total):
                                                if total > 0:
                                                    up_bar.progress(min(sent / total, 1.0))
                                                    up_status.info(f"📤 {sent/1_048_576:.1f} MB / {total/1_048_576:.1f} MB")

                                            try:
                                                up_status.info("🔐 Authenticating with Google...")
                                                from yt_uploader import upload_video, upload_thumbnail, move_to_archive
                                                result = upload_video(
                                                    video_path=video_path,
                                                    title=lib_title,
                                                    description=lib_desc,
                                                    tags=lib_tags_list,
                                                    category_id=lib_meta.get("category_id", "27"),
                                                    privacy=lib_privacy,
                                                    language=lib_meta.get("language", "en"),
                                                    playlist_id=lib_playlist.strip() or None,
                                                    progress_callback=lib_on_progress,
                                                )
                                                if thumb_path:
                                                    up_status.info("🖼️ Setting thumbnail...")
                                                    upload_thumbnail(result["video_id"], thumb_path)

                                                up_bar.progress(1.0)
                                                st.session_state[result_key] = result
                                                up_status.success(f"✅ Uploaded as **{lib_privacy}**!")
                                                st.code(result["url"])

                                                # Move to HDD
                                                if lib_hdd and lib_hdd.strip() and os.path.isdir(lib_hdd.strip()):
                                                    try:
                                                        new_path = move_to_archive(topic_dir_lib, lib_hdd.strip())
                                                        st.success(f"💾 Moved to: `{new_path}`")
                                                    except Exception as mv_err:
                                                        st.warning(f"⚠️ Upload done but move failed: {mv_err}")
                                                elif lib_hdd and lib_hdd.strip():
                                                    st.warning(f"⚠️ Path `{lib_hdd.strip()}` not found/mounted.")

                                            except Exception as e:
                                                up_status.error(f"Upload failed: {e}")

                                if st.session_state[result_key]:
                                    prev = st.session_state[result_key]
                                    st.info(f"📤 Uploaded: [{prev['url']}]({prev['url']}) — **{prev['privacy']}**")

                        with st.expander("Raw Script JSON"):
                            st.json(data)

                    except Exception as e:
                        st.error(f"Could not load script: {e}")


# ───────────────────────────────────────────────────────────
# TAB 3: Trending Topics
# ───────────────────────────────────────────────────────────
with tab3:
    st.header("🔥 Trending Topics")
    st.markdown(
        "Pulls today's trending YouTube videos in **Education, News, Science, and Entertainment**, "
        "then uses the local LLM to extract philosophical dialectic angles from them."
    )

    if not os.path.exists("client_secret.json"):
        st.warning("🔐 `client_secret.json` required for YouTube API access. Add it to the project directory.")
    else:
        tr_col1, tr_col2, tr_col3 = st.columns([2, 1, 1])
        with tr_col1:
            region_options = {
                "🇮🇳 India (IN)": "IN",
                "🇺🇸 United States (US)": "US",
                "🇬🇧 United Kingdom (GB)": "GB",
                "🇦🇺 Australia (AU)": "AU",
                "🇨🇦 Canada (CA)": "CA",
            }
            selected_region_label = st.selectbox(
                "🌍 Region",
                options=list(region_options.keys()),
                index=0,
                key="trend_region"
            )
            selected_region = region_options[selected_region_label]

        with tr_col2:
            n_topics = st.slider("Topics to suggest", min_value=4, max_value=12, value=8, step=2)

        with tr_col3:
            st.markdown("&nbsp;", unsafe_allow_html=True)  # vertical align
            fetch_btn = st.button("🔄 Fetch Trending Topics", type="primary", key="fetch_trends_btn")

        if fetch_btn:
            with st.spinner("📡 Fetching YouTube trending data + extracting philosophical angles..."):
                try:
                    from yt_trends import get_trending_topic_suggestions
                    result = get_trending_topic_suggestions(
                        region_code=selected_region,
                        n_suggestions=n_topics,
                    )
                    st.session_state.trend_results = result
                except Exception as e:
                    st.error(f"Trending fetch failed: {e}")

        trends = st.session_state.trend_results
        if trends:
            if trends.get("error"):
                st.error(trends["error"])
            else:
                st.caption(
                    f"📊 Analysed **{trends['raw_video_count']}** trending videos · "
                    f"Region: **{trends['region']}** · "
                    f"Extracted **{len(trends['topics'])}** philosophical topics"
                )
                st.divider()

                topics = trends["topics"]
                # Display in a 2-column card grid
                for i in range(0, len(topics), 2):
                    cols = st.columns(2)
                    for j, col in enumerate(cols):
                        if i + j >= len(topics):
                            break
                        t = topics[i + j]
                        with col:
                            with st.container(border=True):
                                st.markdown(f"### {t['topic']}")
                                st.caption(f"📌 {t['category']}")
                                if t.get("rationale"):
                                    st.markdown(f"*{t['rationale']}*")
                                if st.button(
                                    "⚡ Generate script for this topic",
                                    key=f"trend_pick_{i+j}",
                                    type="secondary",
                                ):
                                    # Pre-fill the topic and switch to Generator tab
                                    st.session_state.prefill_topic = t["topic"]
                                    st.session_state.phase = 1
                                    st.session_state.output_data = None
                                    st.info(f"✅ Topic copied: **{t['topic']}** — switch to the ⚡ Generator tab to start.")

