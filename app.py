import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, storage
import json
import streamlit.components.v1 as components

st.set_page_config(page_title="Affinity Chart", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
#MainMenu, footer, header { visibility: hidden; }
.stApp { background: #06091e; }
.block-container { padding: 1rem 1rem 0; }
[data-testid="stSidebar"] { background: #080e28; border-right: 1px solid #1e3270; }
.stButton > button {
    background: #0e1c52; color: #80a8e8; border: 1px solid #2a4890;
    font-size: 13px; letter-spacing: 1px; border-radius: 3px;
}
.stButton > button:hover { background: #1a2e70; border-color: #4a78c8; color: #c0d8ff; }
.stTextInput input { background: #080e28 !important; color: #c0d8ff !important; border-color: #2a4890 !important; }
.stRadio label, .stRadio > div { color: #80a8e8 !important; }
.stTabs [data-baseweb="tab"] { color: #5080c0; }
.stTabs [aria-selected="true"] { color: #80b8f8 !important; border-bottom-color: #4a78c8 !important; }
h1, h2, h3 { color: #80b8f8 !important; font-family: monospace; letter-spacing: 2px; }
p, label, .stMarkdown { color: #8098c8 !important; }
hr { border-color: #1e3270; }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def init_firebase():
    if not firebase_admin._apps:
        creds_dict = json.loads(st.secrets["firebase"]["credentials"])
        cred = credentials.Certificate(creds_dict)
        firebase_admin.initialize_app(cred, {
            "storageBucket": st.secrets["firebase"]["storage_bucket"]
        })
    return firestore.client(), storage.bucket()

db, bucket = init_firebase()

def load_data(graph_type):
    col = graph_type.lower()
    p = db.collection(col).document("people").get()
    c = db.collection(col).document("connections").get()
    return (
        p.to_dict().get("list", []) if p.exists else [],
        c.to_dict().get("list", []) if c.exists else []
    )

def save_people(graph_type, people):
    db.collection(graph_type.lower()).document("people").set({"list": people})

def save_connections(graph_type, connections):
    db.collection(graph_type.lower()).document("connections").set({"list": connections})

def upload_to_storage(data, path, content_type):
    blob = bucket.blob(path)
    blob.upload_from_string(data, content_type=content_type)
    blob.make_public()
    return blob.public_url

def get_storage_url(path):
    blob = bucket.blob(path)
    if blob.exists():
        blob.make_public()
        return blob.public_url
    return None

def get_settings():
    ref = db.collection("settings").document("preferences").get()
    return ref.to_dict() if ref.exists else {"autoplay": False}

def save_settings(settings):
    db.collection("settings").document("preferences").set(settings)

# Cache stable values in session state so audio HTML never changes during normal use
if 'music_url' not in st.session_state:
    st.session_state['music_url'] = get_storage_url("music/refugee_camp.mp3")
if 'autoplay' not in st.session_state:
    prefs = get_settings()
    st.session_state['autoplay'] = prefs.get('autoplay', False)

REL_TYPES = {
    "Know each other": {"color": "#C8A020", "shape": "pentagon"},
    "Friends":         {"color": "#3db832", "shape": "square"},
    "Great friends":   {"color": "#2080d8", "shape": "circle"},
    "Best friends":    {"color": "#7050c8", "shape": "hexagon"},
    "In relationship": {"color": "#b02880", "shape": "heart_rel"},
    "Married":         {"color": "#e855a0", "shape": "heart_married"},
    "Don't speak":     {"color": "#d02020", "shape": "triangle"},
}

def build_graph_html(people, connections, image_urls):
    nodes = [{"id": p, "image": image_urls.get(p, "")} for p in people]
    links = []
    for conn in connections:
        rel = conn.get("relationship", "Know each other")
        cfg = REL_TYPES.get(rel, REL_TYPES["Know each other"])
        links.append({
            "source": conn["from"], "target": conn["to"],
            "relationship": rel, "color": cfg["color"], "shape": cfg["shape"],
        })
    data_json = json.dumps({"nodes": nodes, "links": links})

    return f"""<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#06091e;overflow:hidden;font-family:sans-serif;touch-action:none}}
svg{{width:100vw;height:100vh;display:block;cursor:grab}}
svg:active{{cursor:grabbing}}
.n-name{{fill:#a0c8ff;font-size:11px;text-anchor:middle;pointer-events:none}}
.n-init{{fill:#6090e0;font-size:15px;font-weight:500;text-anchor:middle;dominant-baseline:middle;pointer-events:none}}
</style>
</head>
<body>
<svg id="g"></svg>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<script>
const data = {data_json};
const W = window.innerWidth, H = window.innerHeight;
const svg = d3.select("#g").attr("viewBox",[0,0,W,H]);
const defs = svg.append("defs");

const container = svg.append("g").attr("id","container");

const zoom = d3.zoom()
  .scaleExtent([0.05,10])
  .on("zoom",(e)=>{{ container.attr("transform",e.transform); }});
svg.call(zoom).on("dblclick.zoom",null);

data.nodes.forEach(n=>{{
  const sid=n.id.replace(/[^a-zA-Z0-9]/g,"-");
  defs.append("clipPath").attr("id","clip-"+sid)
    .append("circle").attr("r",28).attr("cx",0).attr("cy",0);
  if(n.image){{
    const pat=defs.append("pattern")
      .attr("id","img-"+sid)
      .attr("patternUnits","objectBoundingBox")
      .attr("width",1).attr("height",1);
    pat.append("image").attr("href",n.image)
      .attr("width",56).attr("height",56)
      .attr("preserveAspectRatio","xMidYMid slice");
  }}
}});

function drawIcon(g,shape,color){{
    const s=16, dc="#06091e";
    if(shape==="pentagon"){{
      const pts=[...Array(5)].map((_,i)=>{{const a=(i*72-90)*Math.PI/180;return[s*Math.cos(a),s*Math.sin(a)]}});
      g.append("polygon").attr("points",pts.map(p=>p.join(",")).join(" ")).attr("fill",color).attr("stroke",dc).attr("stroke-width",2);
      g.append("rect").attr("x",-s*0.55).attr("y",-s*0.15).attr("width",s*0.375).attr("height",s*0.375).attr("fill",dc).attr("rx",0.8);
      g.append("rect").attr("x",s*0.175).attr("y",-s*0.15).attr("width",s*0.375).attr("height",s*0.375).attr("fill",dc).attr("rx",0.8);
      g.append("rect").attr("x",-s*0.45).attr("y",s*0.375).attr("width",s*0.9).attr("height",s*0.22).attr("fill",dc).attr("rx",0.8);
    }}else if(shape==="square"){{
      g.append("rect").attr("x",-s).attr("y",-s).attr("width",s*2).attr("height",s*2).attr("fill",color).attr("stroke",dc).attr("stroke-width",2).attr("rx",2.4);
      g.append("rect").attr("x",-s*0.55).attr("y",-s*0.22).attr("width",s*0.375).attr("height",s*0.375).attr("fill",dc).attr("rx",0.8);
      g.append("rect").attr("x",s*0.175).attr("y",-s*0.22).attr("width",s*0.375).attr("height",s*0.375).attr("fill",dc).attr("rx",0.8);
      g.append("path").attr("d",`M ${{-s*0.52}} ${{s*0.3}} Q 0 ${{s*0.72}} ${{s*0.52}} ${{s*0.3}}`).attr("fill","none").attr("stroke",dc).attr("stroke-width",s*0.125).attr("stroke-linecap","round");
    }}else if(shape==="circle"){{
      g.append("circle").attr("r",s).attr("fill",color).attr("stroke",dc).attr("stroke-width",2);
      g.append("rect").attr("x",-s*0.55).attr("y",-s*0.22).attr("width",s*0.4).attr("height",s*0.4).attr("fill",dc).attr("rx",0.8);
      g.append("rect").attr("x",s*0.15).attr("y",-s*0.22).attr("width",s*0.4).attr("height",s*0.4).attr("fill",dc).attr("rx",0.8);
      g.append("path").attr("d",`M ${{-s*0.55}} ${{s*0.28}} Q 0 ${{s*0.72}} ${{s*0.55}} ${{s*0.28}}`).attr("fill","none").attr("stroke",dc).attr("stroke-width",s*0.14).attr("stroke-linecap","round");
    }}else if(shape==="hexagon"){{
      const pts=[...Array(6)].map((_,i)=>{{const a=i*60*Math.PI/180;return[s*Math.cos(a),s*Math.sin(a)]}});
      g.append("polygon").attr("points",pts.map(p=>p.join(",")).join(" ")).attr("fill",color).attr("stroke",dc).attr("stroke-width",2);
      g.append("path").attr("d",`M ${{-s*0.58}} ${{-s*0.12}} Q ${{-s*0.34}} ${{-s*0.5}} ${{-s*0.11}} ${{-s*0.12}}`).attr("fill","none").attr("stroke",dc).attr("stroke-width",s*0.125).attr("stroke-linecap","round");
      g.append("path").attr("d",`M ${{s*0.11}} ${{-s*0.12}} Q ${{s*0.34}} ${{-s*0.5}} ${{s*0.58}} ${{-s*0.12}}`).attr("fill","none").attr("stroke",dc).attr("stroke-width",s*0.125).attr("stroke-linecap","round");
      g.append("path").attr("d",`M ${{-s*0.58}} ${{s*0.28}} Q 0 ${{s*0.72}} ${{s*0.58}} ${{s*0.28}}`).attr("fill","none").attr("stroke",dc).attr("stroke-width",s*0.15).attr("stroke-linecap","round");
    }}else if(shape==="heart_rel"||shape==="heart_married"){{
      g.append("path").attr("d",`M 0 ${{s*0.625}} C ${{-s}} 0 ${{-s*1.25}} ${{-s*0.625}} ${{-s*0.594}} ${{-s*0.906}} C ${{-s*0.25}} ${{-s*1.0625}} 0 ${{-s*0.6875}} 0 ${{-s*0.5625}} C 0 ${{-s*0.6875}} ${{s*0.25}} ${{-s*1.0625}} ${{s*0.594}} ${{-s*0.906}} C ${{s*1.25}} ${{-s*0.625}} ${{s}} 0 0 ${{s*0.625}} Z`).attr("fill",color).attr("stroke",dc).attr("stroke-width",2);
      if(shape==="heart_married"){{
        [[-s*0.36,-s*0.09],[s*0.36,-s*0.09]].forEach(([hx,hy])=>{{
          const hs=s*0.42;
          g.append("path").attr("d",`M ${{hx}} ${{hy+hs*0.625}} C ${{hx-hs}} ${{hy}} ${{hx-hs*1.25}} ${{hy-hs*0.625}} ${{hx-hs*0.594}} ${{hy-hs*0.906}} C ${{hx-hs*0.25}} ${{hy-hs*1.0625}} ${{hx}} ${{hy-hs*0.6875}} ${{hx}} ${{hy-hs*0.5625}} C ${{hx}} ${{hy-hs*0.6875}} ${{hx+hs*0.25}} ${{hy-hs*1.0625}} ${{hx+hs*0.594}} ${{hy-hs*0.906}} C ${{hx+hs*1.25}} ${{hy-hs*0.625}} ${{hx+hs}} ${{hy}} ${{hx}} ${{hy+hs*0.625}} Z`).attr("fill",dc);
        }});
        g.append("path").attr("d",`M ${{-s*0.52}} ${{s*0.03}} Q 0 ${{s*0.39}} ${{s*0.52}} ${{s*0.03}}`).attr("fill","none").attr("stroke",dc).attr("stroke-width",s*0.125).attr("stroke-linecap","round");
      }}else{{
        g.append("rect").attr("x",-s*0.55).attr("y",-s*0.44).attr("width",s*0.375).attr("height",s*0.375).attr("fill",dc).attr("rx",0.8);
        g.append("rect").attr("x",s*0.175).attr("y",-s*0.44).attr("width",s*0.375).attr("height",s*0.375).attr("fill",dc).attr("rx",0.8);
        g.append("path").attr("d",`M ${{-s*0.52}} ${{s*0.03}} Q 0 ${{s*0.39}} ${{s*0.52}} ${{s*0.03}}`).attr("fill","none").attr("stroke",dc).attr("stroke-width",s*0.125).attr("stroke-linecap","round");
      }}
    }}else if(shape==="triangle"){{
      const h=s*1.2;
      g.append("polygon").attr("points",`0,${{-h}} ${{h}},${{h*0.7}} ${{-h}},${{h*0.7}}`).attr("fill",color).attr("stroke",dc).attr("stroke-width",2);
      g.append("rect").attr("x",-s*0.58).attr("y",-s*0.19).attr("width",s*0.375).attr("height",s*0.31).attr("fill",dc).attr("rx",0.8).attr("transform","rotate(-18)");
      g.append("rect").attr("x",s*0.2).attr("y",-s*0.19).attr("width",s*0.375).attr("height",s*0.31).attr("fill",dc).attr("rx",0.8).attr("transform","rotate(18)");
      g.append("path").attr("d",`M ${{-s*0.55}} ${{s*0.5}} Q 0 ${{s*0.125}} ${{s*0.55}} ${{s*0.5}}`).attr("fill","none").attr("stroke",dc).attr("stroke-width",s*0.125).attr("stroke-linecap","round");
    }}
  }}

const sim=d3.forceSimulation(data.nodes)
  .force("link",d3.forceLink(data.links).id(d=>d.id).distance(180))
  .force("charge",d3.forceManyBody().strength(-320))
  .force("center",d3.forceCenter(W/2,H/2))
  .force("collision",d3.forceCollide().radius(55));

// After initial layout, pin all nodes and stop simulation
setTimeout(()=>{{
  data.nodes.forEach(n=>{{ if(n.fx==null){{ n.fx=n.x; n.fy=n.y; }} }});
  sim.alphaTarget(0).stop();
}},2500);

const eGrp=container.append("g"),iGrp=container.append("g"),nGrp=container.append("g");

const edges=eGrp.selectAll("line").data(data.links).join("line")
  .attr("stroke",d=>d.color).attr("stroke-width",2).attr("stroke-opacity",0.6);

const icons=iGrp.selectAll("g").data(data.links).join("g");
icons.each(function(d){{drawIcon(d3.select(this),d.shape,d.color)}});

const drag=d3.drag()
  .on("start",(e)=>{{
    e.sourceEvent.stopPropagation();
    if(!e.active) sim.alphaTarget(0.1).restart();
    e.subject.fx=e.subject.x;
    e.subject.fy=e.subject.y;
  }})
  .on("drag",(e)=>{{
    e.subject.fx=e.x;
    e.subject.fy=e.y;
  }})
  .on("end",(e)=>{{
    if(!e.active) sim.alphaTarget(0);
    // fx/fy intentionally kept — node stays where dropped
  }});

const nodes=nGrp.selectAll("g").data(data.nodes).join("g").call(drag);

nodes.append("circle").attr("r",33).attr("fill","none").attr("stroke","#1e3a80").attr("stroke-width",1.5).attr("opacity",0.6);

nodes.each(function(d){{
  const g=d3.select(this);
  const sid=d.id.replace(/[^a-zA-Z0-9]/g,"-");
  if(d.image){{
    g.append("circle").attr("r",28).attr("fill",`url(#img-${{sid}})`).attr("stroke","#4a78c8").attr("stroke-width",2.5).attr("clip-path",`url(#clip-${{sid}})`);
  }}else{{
    g.append("circle").attr("r",28).attr("fill","#0e1c52").attr("stroke","#4a78c8").attr("stroke-width",2.5);
    g.append("text").attr("class","n-init").attr("dy","0.1em")
      .text(d.id.split(" ").map(w=>w[0]||"").join("").toUpperCase().slice(0,2));
  }}
  g.append("text").attr("class","n-name").attr("y",45)
    .text(d.id.length>14?d.id.slice(0,13)+"…":d.id);
}});

sim.on("tick",()=>{{
  edges.attr("x1",d=>d.source.x).attr("y1",d=>d.source.y)
       .attr("x2",d=>d.target.x).attr("y2",d=>d.target.y);
  icons.attr("transform",d=>`translate(${{(d.source.x+d.target.x)/2}},${{(d.source.y+d.target.y)/2}})`);
  nodes.attr("transform",d=>`translate(${{d.x}},${{d.y}})`);
}});

window.addEventListener("resize",()=>{{
  const nw=window.innerWidth,nh=window.innerHeight;
  svg.attr("viewBox",[0,0,nw,nh]);
}});
</script>
</body>
</html>"""

# ── UI ─────────────────────────────────────────────────────────────────────────

# Audio player — lives in its own separate component so it never reloads on graph changes
music_url = st.session_state['music_url']
autoplay = st.session_state['autoplay']
if music_url:
    ap_attr = 'autoplay' if autoplay else ''
    init_btn = 'PAUSE' if autoplay else 'PLAY'
    audio_html = f"""<style>
body{{margin:0;background:transparent;display:flex;align-items:center;gap:8px;padding:4px 8px}}
button{{background:#0e1c52;border:1px solid #2a4890;color:#80a8e8;padding:4px 12px;border-radius:3px;cursor:pointer;font-size:11px;letter-spacing:1px;font-family:sans-serif}}
button:hover{{background:#1a2e70;color:#c0d8ff}}
#lbl{{color:#5070a8;font-size:10px;letter-spacing:2px;font-family:sans-serif}}
</style>
<audio id="a" {ap_attr} loop src="{music_url}"></audio>
<span id="lbl">♪ IN THE REFUGEE CAMP</span>
<button id="pb" onclick="var a=document.getElementById('a');if(a.paused){{a.play();this.textContent='PAUSE'}}else{{a.pause();this.textContent='PLAY'}}">{init_btn}</button>
<button onclick="var a=document.getElementById('a');a.muted=!a.muted;this.textContent=a.muted?'UNMUTE':'MUTE'">MUTE</button>"""
    components.html(audio_html, height=44)

c1, c2 = st.columns([2, 8])
with c1:
    graph_type = st.radio("", ["Friends", "Family"], horizontal=True, label_visibility="collapsed")
with c2:
    st.markdown("<h2 style='padding-top:0.4rem;text-align:center'>⬡ AFFINITY CHART</h2>", unsafe_allow_html=True)

st.markdown("<hr style='margin:0.4rem 0'>", unsafe_allow_html=True)

people, connections = load_data(graph_type)
image_urls = {}
for person in people:
    url = get_storage_url(f"{graph_type.lower()}/images/{person}")
    if url:
        image_urls[person] = url

components.html(build_graph_html(people, connections, image_urls), height=520, scrolling=False)

st.markdown("<hr style='margin:0.4rem 0'>", unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["👤  People", "🔗  Connections", "⚙️  Settings"])

with tab1:
    ca, cb = st.columns([3, 2])
    with ca:
        new_name = st.text_input("Name", placeholder="Enter name...")
        img_file = st.file_uploader("Profile photo (optional)", type=["jpg","jpeg","png"], key="img_up")
    with cb:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("➕ Add Person", use_container_width=True):
            if new_name and new_name not in people:
                people.append(new_name)
                save_people(graph_type, people)
                if img_file:
                    upload_to_storage(img_file.read(), f"{graph_type.lower()}/images/{new_name}", img_file.type)
                st.rerun()
            elif new_name in people:
                st.warning("Already added!")
    st.markdown("---")
    for i, person in enumerate(people):
        r1, r2, r3 = st.columns([4, 2, 1])
        r1.write(person)
        img_upd = r2.file_uploader("", type=["jpg","jpeg","png"], key=f"upd_{i}", label_visibility="collapsed")
        if img_upd:
            upload_to_storage(img_upd.read(), f"{graph_type.lower()}/images/{person}", img_upd.type)
            st.rerun()
        if r3.button("✕", key=f"del_{i}"):
            people.remove(person)
            connections = [c for c in connections if c["from"] != person and c["to"] != person]
            save_people(graph_type, people)
            save_connections(graph_type, connections)
            st.rerun()

with tab2:
    if len(people) >= 2:
        ca, cb = st.columns(2)
        person_a = ca.selectbox("Person A", people)
        person_b = cb.selectbox("Person B", [p for p in people if p != person_a])
        relationship = st.selectbox("Relationship type", list(REL_TYPES.keys()))
        if st.button("➕ Add Connection", use_container_width=True):
            exists = any(
                (c["from"]==person_a and c["to"]==person_b) or
                (c["from"]==person_b and c["to"]==person_a)
                for c in connections
            )
            if not exists:
                connections.append({"from": person_a, "to": person_b, "relationship": relationship})
                save_connections(graph_type, connections)
                st.rerun()
            else:
                st.warning("Connection already exists!")
        st.markdown("---")
        for i, conn in enumerate(connections):
            ca, cb = st.columns([5, 1])
            ca.markdown(f"{conn['from']} ↔ {conn['to']} — *{conn.get('relationship','')}*")
            if cb.button("✕", key=f"dc_{i}"):
                connections.pop(i)
                save_connections(graph_type, connections)
                st.rerun()
    else:
        st.info("Add at least 2 people first!")

with tab3:
    st.markdown("**Autoplay music on load**")
    new_autoplay = st.toggle("Enable autoplay", value=st.session_state['autoplay'])
    if new_autoplay != st.session_state['autoplay']:
        st.session_state['autoplay'] = new_autoplay
        save_settings({"autoplay": new_autoplay})
        st.rerun()
    st.markdown("---")
    st.markdown("**Music file**")
    music_file = st.file_uploader("", type=["mp3"], key="music_up", label_visibility="collapsed")
    if music_file:
        with st.spinner("Uploading..."):
            upload_to_storage(music_file.read(), "music/refugee_camp.mp3", "audio/mpeg")
            st.session_state['music_url'] = get_storage_url("music/refugee_camp.mp3")
        st.success("Music uploaded!")
    if music_url:
        st.success("✓ Music file is ready")
    else:
        st.warning("No music uploaded yet")
