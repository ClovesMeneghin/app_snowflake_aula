import streamlit as st
import pandas as pd
import plotly.express as px
from snowflake.snowpark import Session
from datetime import datetime

# CONFIGURAÇÃO
st.set_page_config(
    page_title="COVID-19 Dashboard",
    page_icon=":biohazard:",
    layout="wide",
    initial_sidebar_state="expanded"
)

# HEADER
st.title("COVID-19 Dashboard")
st.markdown("Este dashboard apresenta dados sobre a pandemia de COVID-19, incluindo casos, mortes e vacinação em diferentes países.")

st.sidebar.header("Configurações")

url = "https://raw.githubusercontent.com/owid/covid-19-data/master/public/data/owid-covid-data.csv"

sum_deaths = 0  # Inicializa a variável sum_deaths para evitar erro de referência antes da atribuição



# Estrutura do código de carga (esqueleto)
connection_parameters = {
"user": st.secrets["snowflake"]["user"],
"password": st.secrets["snowflake"]["password"],
"account": st.secrets["snowflake"]["account"],
"warehouse": st.secrets["snowflake"]["warehouse"],
"database": "TEST_DB",
"schema": "PUBLIC",
"role": st.secrets["snowflake"]["role"]
}

if st.sidebar.button("Carregar Dados no Snowflake"):
    try:
        with st.spinner("Baixando dados COVID-19..."):
            df = pd.read_csv(url)
            paises = ['Brazil', 'United States', 'India', 'Germany', 'South Africa', 'Japan']
            df = df[df['location'].isin(paises)]
            df = df[df['date'] >= '2021-01-01'] # opcional: restringe o período
            st.sidebar.success(f"✅ {df.shape[0]} linhas baixadas")

        with st.spinner("Enviando para Snowflake..."):
            session = Session.builder.configs(connection_parameters).create()
            session.sql("CREATE DATABASE IF NOT EXISTS TEST_DB").collect()
            session.sql("USE DATABASE TEST_DB").collect()
            session.sql("USE SCHEMA PUBLIC").collect()
            session.write_pandas(df, "TB_COVID", auto_create_table=True, overwrite=True)
            session.close()
            st.sidebar.success("✅ Dados atualizados no Snowflake!")
            st.balloons()
    except Exception as e:
        st.sidebar.error(f"❌ Erro: {e}")
        

if st.sidebar.button("Carregar Dashboard"):
    try:
        with st.spinner("Conectando ao Snowflake..."):
            session = Session.builder.configs(connection_parameters).create()
            session.sql("USE DATABASE TEST_DB").collect()
            session.sql("USE SCHEMA PUBLIC").collect()

            df = session.table("TB_COVID").to_pandas()
            session.close()

            # Normalizar nomes das colunas (converter para minúsculas)
            df.columns = df.columns.str.lower()

            # Converter colunas de data
            date_cols = [col for col in df.columns if 'timestamp' in col or 'date' in col]
            for col in date_cols:
                df[col] = pd.to_datetime(df[col], errors='coerce')

            st.session_state['df'] = df
            st.sidebar.success(f"✅ {len(df)} casos carregados")

    except Exception as e:
        st.sidebar.error(f"❌ Erro ao carregar: {e}")
        st.sidebar.error(f"Detalhes: {str(e)}")
        st.sidebar.info("💡 Se a tabela não existe ainda, clique primeiro em 'Carregar/Atualizar Dados no Snowflake'")
        

if 'df' in st.session_state:
    df = st.session_state['df']
            
    st.sidebar.divider()
    st.sidebar.header("Filtros")

    paises_disponiveis = df['location'].unique().tolist()
    paises_selecionados = st.sidebar.multiselect(
        "Selecione os países",
        options=paises_disponiveis,
        default=paises_disponiveis
    )

    data_min = df['date'].min().to_pydatetime()
    data_max = df['date'].max().to_pydatetime()

    periodo = st.sidebar.slider(
        "Selecione o período",
        min_value=data_min,
        max_value=data_max,
        value=(data_min, data_max),
        format="MM/YYYY"
    )

    df = df[
        (df['location'].isin(paises_selecionados)) &
        (df['date'] >= periodo[0]) &
        (df['date'] <= periodo[1])
    ]    
    
    # MÉTRICAS PRINCIPAIS
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        sum_cases = int(df.groupby('location')['total_cases'].max().sum())
        st.metric("Total de Casos", f"{sum_cases:,}")
        #st.metric("Total de Casos", f"{df['total_cases'].max():,}")

    with col2:
        if 'total_deaths' in df.columns:
            sum_deaths = int(df.groupby('location')['total_deaths'].max().sum())
            st.metric("Total de Óbitos", f"{sum_deaths:,}")
            #st.metric("Total de Óbitos", f"{df['total_deaths'].max():,}")
        else:
            st.metric("Total de Óbitos", "N/A")

    with col3:
        pct_deaths = (sum_deaths / sum_cases * 100) if sum_cases > 0 else 0
        st.metric("Porcentagem de Óbitos entre Casos", f"{pct_deaths:.2f}%")
        #st.metric("Total de Casos", f"{df['total_cases'].max():,}")
    
    with col4:
        if 'location' in df.columns:
            st.metric("Países Analisados", f"{df['location'].nunique():,}")
        else:
            st.metric("Países Analisados", "N/A")

    
    st.divider()

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📈 Evolução de Casos", "📊 Total de Óbitos", "💉 Vacinação", "📉 Correlação de Casos", "📋 Dados Brutos", "🔍 SQL Query"])

    with tab1:
        st.subheader("Análise Temporal de Casos")

        fig = px.line(
            df,
            x='date',
            y='new_cases_smoothed_per_million',       # versão suavizada evita ruído dos fins de semana
            color='location',             # uma linha por país
            line_shape='linear',
            title='Evolução de Novos Casos de COVID-19 por milhão de habitantes (média móvel 7 dias)',
            labels={
                'date': 'Data',
                'new_cases_smoothed_per_million': 'Novos Casos (média 7 dias)',
                'location': 'País'
            }
        )
        st.plotly_chart(fig, width='stretch')
        
    with tab2:
        st.subheader("Comparação de Óbitos Totais")

        # Pega o valor mais recente de cada país
        df_mortes = df.groupby('location')['total_deaths'].max().reset_index()

        fig = px.bar(
            df_mortes,
            x='location',
            y='total_deaths',
            color='location',
        title='Total de Óbitos por COVID-19',
            labels={
                'location': 'País',
                'total_deaths': 'Total de Óbitos'
            }
        )
        st.plotly_chart(fig, width='stretch')

    with tab3:
        st.subheader("Proporção de Vacinados (1 dose) por País")

        # Verifica se o utilizador selecionou algum país no filtro lateral
        if len(paises_selecionados) > 0:
            
            # Ciclo para iterar sobre cada país selecionado
            for pais in paises_selecionados:
                
                # Filtra os dados apenas para o país atual do ciclo
                df_pais = df[df['location'] == pais]
                
                # Fica com a "fotografia" mais recente (última linha) em que há dados de vacinação
                linha_recente = df_pais.dropna(subset=['people_vaccinated']).sort_values('date').iloc[-1]
                
                # Calcula as fatias
                total_vacinados = linha_recente['people_vaccinated']
                nao_vacinados = linha_recente['population'] - total_vacinados
                
                # Cria o mini dataframe para o gráfico circular (pizza)
                dados_pizza = pd.DataFrame({
                    'Status': ['Vacinados (1ª Dose)', 'Não Vacinados'],
                    'Quantidade': [total_vacinados, nao_vacinados]
                })
                
                # Monta o gráfico
                fig = px.pie(
                    dados_pizza,
                    names='Status',
                    values='Quantidade',
                    title=f"Proporção de Vacinação: {pais}", 
                    hole=0.4,        # Estilo donut
                    color='Status',
                    color_discrete_map={
                        'Vacinados (1ª Dose)': '#2ca02c',
                        'Não Vacinados': '#d62728'
                    }
                )
                
                # Ajusta as margens para que os gráficos não fiquem demasiado afastados verticalmente
                fig.update_layout(margin=dict(t=50, b=20, l=0, r=0))
                
                # Plota o gráfico diretamente, o que os irá empilhar verticalmente
                st.plotly_chart(fig, width='stretch')
                
                # (Opcional) Adiciona um separador visual entre os gráficos, caso haja muitos
                st.divider()
                
        else:
            st.warning("Selecione pelo menos um país na barra lateral para visualizar.")
                
        
   
    with tab4:
        st.subheader("Relação entre População e Total de Casos")

        # Pega o valor mais recente válido de cada país
        df_scatter = df.groupby('location')[['population', 'total_cases']].max().reset_index()

        fig = px.scatter(
            df_scatter,
            x='population',
            y='total_cases',
            color='location',
            size='total_cases',            # tamanho do ponto proporcional ao total de casos
            title='Relação entre População e Total de Casos',
            labels={
                'population': 'População',
                'total_cases': 'Total de Casos',
                'location': 'País'
            }
        )
        st.plotly_chart(fig, width='stretch')
        
        st.subheader("Relação entre População e Total de Óbitos")

        # Pega o valor mais recente válido de cada país
        df_scatter = df.groupby('location')[['population', 'total_deaths']].max().reset_index()

        fig = px.scatter(
            df_scatter,
            x='population',
            y='total_deaths',
            color='location',
            size='total_deaths',            # tamanho do ponto proporcional ao total de óbitos
            title='Relação entre População e Total de Óbitos',
            labels={
                'population': 'População',
                'total_deaths': 'Total de Óbitos',
                'location': 'País'
            }
        )
        st.plotly_chart(fig, width='stretch')
# salvar em st.session_state
     

    with tab5:
        st.subheader("Dados Brutos")
        st.dataframe(df, width='stretch')
        
        if st.download_button("Download CSV", data=df.to_csv(index=False), file_name="covid_data.csv", mime="text/csv"):
            st.success("Arquivo CSV baixado com sucesso!")
            
            
    import re

    with tab6:
        with st.expander("🔍 Ver Colunas Disponíveis"):
            st.write(list(df.columns))
            
        st.subheader("Consulta SQL Personalizada")
        sql_query = st.text_area("Digite sua consulta SQL (ex: SELECT * FROM TB_COVID LIMIT 10):", height=150)

        if st.button("Executar Consulta"):
            # 1. Limpa espaços e joga tudo para maiúsculo para facilitar a verificação
            query_limpa = sql_query.strip().upper()

            # 2. Lista de comandos proibidos (DML e DDL)
            palavras_proibidas = [r"\bDROP\b", r"\bDELETE\b", r"\bUPDATE\b", r"\bINSERT\b", r"\bALTER\b", r"\bTRUNCATE\b"]
        
            # 3. Verifica se tem alguma palavra proibida na string
            tem_palavra_proibida = any(re.search(palavra, query_limpa) for palavra in palavras_proibidas)

            # 4. A regra de ouro: Tem que começar com SELECT e não pode ter palavras destrutivas
            if not query_limpa.startswith("SELECT") or tem_palavra_proibida:
                st.error("❌ Operação negada. Apenas consultas de leitura (SELECT) são permitidas por segurança.")
            else:
                # Se passou no filtro, executa a consulta normalmente
                try:
                    session = Session.builder.configs(connection_parameters).create()
                    session.sql("USE DATABASE TEST_DB").collect()
                    session.sql("USE SCHEMA PUBLIC").collect()

                    result_df = session.sql(sql_query).to_pandas()
                    session.close()

                    st.dataframe(result_df, width='stretch')

                except Exception as e:
                    st.error(f"❌ Erro ao executar a consulta: {e}")
            

else:
    st.info("👈 Clique em 'Carregar/Atualizar Dados no Snowflake' primeiro (só na primeira vez), depois em 'Carregar Dashboard'")
